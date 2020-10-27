import math
from typing import Dict
from unittest.mock import MagicMock, patch

import maya
import pytest
from maya import MayaDT
from nucypher.blockchain.eth.token import NU

from monitor.supply import LAUNCH_DATE, vesting_remaining_factor, DAYS_PER_MONTH, calculate_supply_information, \
    INITIAL_SUPPLY, UNIVERSITY_SUPPLY, CASI_SUPPLY, SAFT2_ALLOCATION_PERCENTAGE, TEAM_ALLOCATION_PERCENTAGE, \
    NUCO_ALLOCATION_PERCENTAGE, SAFT1_ALLOCATION_PERCENTAGE

TEST_REWARDS_PER_MONTH = NU(83_333, 'NU')


@pytest.mark.parametrize('months_transpired', [2, 10, 20, 33, 42, 54, 63, 79, 81, 97, 100])
@pytest.mark.parametrize('vesting_months', [5, 10, 24, 37, 48, 72])
def test_vesting_remaining_factor(months_transpired, vesting_months):
    verify_vesting_reamaining_factor(vesting_months, months_transpired)


@pytest.mark.parametrize('months_transpired', [0, 3, 5, 11, 13, 23, 29, 31, 37, 20, 33, 42, 54, 67, 79, 83, 97, 100])
def test_supply_information(months_transpired):

    # initial values
    max_supply = NU(3_890_000_000, 'NU')
    worklock_supply = NU(225_000_000, 'NU')

    # assume 83,333 NU / month in rewards
    initial_supply_with_rewards = INITIAL_SUPPLY + (months_transpired * TEST_REWARDS_PER_MONTH)

    economics = MagicMock(total_supply=max_supply.to_nunits(),
                          worklock_supply=worklock_supply.to_nunits(),
                          initial_supply=initial_supply_with_rewards.to_nunits())

    future_date = LAUNCH_DATE.add(days=math.ceil(months_transpired * DAYS_PER_MONTH))
    with patch.object(maya, 'now', return_value=future_date):
        supply_information = calculate_supply_information(economics)
        verify_supply_information(supply_information, max_supply, initial_supply_with_rewards,
                                  worklock_supply, future_date)


def verify_vesting_reamaining_factor(vesting_months: int, months_transpired: int):
    future_date = LAUNCH_DATE.add(days=math.ceil(months_transpired * DAYS_PER_MONTH))

    # cliff check
    factor = vesting_remaining_factor(vesting_months=vesting_months, cliff=True, now=future_date)
    if months_transpired >= vesting_months:
        # everything has vested
        assert factor == 0
    else:
        assert factor == 1

    # non-cliff check
    factor = vesting_remaining_factor(vesting_months=vesting_months, cliff=False, now=future_date)
    if months_transpired >= vesting_months:
        # vesting period over
        assert factor == 0
    else:
        assert factor == ((vesting_months - months_transpired) / vesting_months)


def verify_supply_information(supply_information: Dict,
                              max_supply: NU,
                              initial_supply_with_rewards: NU,
                              worklock_supply: NU,
                              future_date: MayaDT):
    assert supply_information['initial_supply']['total_allocated'] == str(round(INITIAL_SUPPLY, 2))

    # Locked
    vest_24_months = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)
    vest_6_months_cliff = vesting_remaining_factor(vesting_months=6, cliff=True, now=future_date)
    vest_3_years_cliff = vesting_remaining_factor(vesting_months=3*12, cliff=True, now=future_date)
    vest_5_years_cliff = vesting_remaining_factor(vesting_months=5*12, cliff=True, now=future_date)

    saft2_supply = NU(value=(SAFT2_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits() * vest_24_months),
                      denomination='NuNit')
    assert supply_information['initial_supply']['locked_allocations']['saft2'] == str(round(saft2_supply, 2))

    team_supply = NU(value=(TEAM_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits() * vest_24_months),
                     denomination='NuNit')
    assert supply_information['initial_supply']['locked_allocations']['team'] == str(round(team_supply, 2))

    nuco_supply = NU(value=(NUCO_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits() * vest_5_years_cliff),
                     denomination='NuNit')
    assert supply_information['initial_supply']['locked_allocations']['company'] == str(round(nuco_supply, 2))

    wl_supply = NU(value=(worklock_supply.to_nunits() * vest_6_months_cliff), denomination='NuNit')
    assert supply_information['initial_supply']['locked_allocations']['worklock'] == str(round(wl_supply, 2))

    university_supply = NU(value=(UNIVERSITY_SUPPLY.to_nunits() * vest_3_years_cliff), denomination='NuNit')
    assert supply_information['initial_supply']['locked_allocations']['university'] == str(round(university_supply, 2))

    total_locked = saft2_supply + team_supply + nuco_supply + wl_supply + university_supply

    # Unlocked
    saft1_supply = NU(value=(SAFT1_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits()), denomination='NuNit')
    assert supply_information['initial_supply']['unlocked_allocations']['saft1'] == str(round(saft1_supply, 2))

    assert supply_information['initial_supply']['unlocked_allocations']['casi'] == str(round(CASI_SUPPLY, 2))
    # TODO 'other' entry\

    remaining_unlocked = INITIAL_SUPPLY - total_locked - saft1_supply - CASI_SUPPLY
    assert supply_information['initial_supply']['unlocked_allocations']['other'] == str(round(remaining_unlocked, 2))

    total_unlocked = saft1_supply + CASI_SUPPLY + remaining_unlocked

    # Staking Rewards
    assert supply_information['staking_rewards_supply']['total_allocated'] == str(
        round(max_supply - INITIAL_SUPPLY, 2))
    assert supply_information['staking_rewards_supply']['staking_rewards_issued'] == str(
        round(initial_supply_with_rewards - INITIAL_SUPPLY, 2)
    )
    assert supply_information['staking_rewards_supply']['staking_rewards_remaining'] == str(
        round(max_supply - initial_supply_with_rewards, 2)
    )

    # Max Supply
    assert supply_information['max_supply'] == str(round(max_supply, 2))

    # Circulating Supply
    assert supply_information['est_circulating_supply'] == str(round(total_unlocked, 2))
