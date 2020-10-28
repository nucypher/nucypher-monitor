from typing import Dict
from unittest.mock import MagicMock, patch

import maya
import pytest
from maya import MayaDT
from nucypher.blockchain.eth.token import NU

from monitor.supply import LAUNCH_DATE, vesting_remaining_factor, DAYS_PER_MONTH, calculate_supply_information, \
    INITIAL_SUPPLY, UNIVERSITY_SUPPLY, CASI_SUPPLY, SAFT2_ALLOCATION_PERCENTAGE, TEAM_ALLOCATION_PERCENTAGE, \
    NUCO_ALLOCATION_PERCENTAGE, SAFT1_ALLOCATION_PERCENTAGE, months_transpired_from_launch

TEST_REWARDS_PER_MONTH = NU(83_333, 'NU')


def test_months_transpired():
    # ensure months transpired match calculation used for locked periods for allocations
    max_time_months = 5*12
    for i in range(1, max_time_months+1):
        lock_periods_used_in_allocation = round(i * DAYS_PER_MONTH)  # calculation used in allocations
        months_transpired = months_transpired_from_launch(LAUNCH_DATE.add(days=lock_periods_used_in_allocation))
        assert months_transpired == i


def test_vesting_remaining_factor_24_months():
    # 1 month later i.e. not yet vested
    months_transpired = 1
    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))
    factor = vesting_remaining_factor(vesting_months=24, cliff=True, now=future_date)  # cliff
    assert factor == 1
    factor = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)  # non-cliff
    assert factor == ((24 - months_transpired)/24)

    # 5 months later i.e. not yet vested
    months_transpired = 5
    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))
    factor = vesting_remaining_factor(vesting_months=24, cliff=True, now=future_date)  # cliff
    assert factor == 1
    factor = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)  # non-cliff
    assert factor == ((24 - months_transpired)/24)

    # 13 months later i.e. not yet vested
    months_transpired = 13
    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))
    factor = vesting_remaining_factor(vesting_months=24, cliff=True, now=future_date)  # cliff
    assert factor == 1
    factor = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)  # non-cliff
    assert factor == ((24 - months_transpired)/24)

    # 23 months later i.e. not yet vested
    months_transpired = 23
    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))
    factor = vesting_remaining_factor(vesting_months=24, cliff=True, now=future_date)  # cliff
    assert factor == 1
    factor = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)  # non-cliff
    assert factor == ((24 - months_transpired) / 24)

    # 24 months later i.e. vested
    months_transpired = 24
    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))
    factor = vesting_remaining_factor(vesting_months=24, cliff=True, now=future_date)  # cliff
    assert factor == 0
    factor = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)  # non-cliff
    assert factor == 0

    # 30 months later i.e. vested
    months_transpired = 30
    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))
    factor = vesting_remaining_factor(vesting_months=24, cliff=True, now=future_date)  # cliff
    assert factor == 0
    factor = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)  # non-cliff
    assert factor == 0


@pytest.mark.parametrize('months_transpired', [2, 10, 20, 33, 42, 54, 63, 79, 81, 97, 100])
@pytest.mark.parametrize('vesting_months', [5, 10, 24, 37, 48, 72])
def test_vesting_remaining_factor(months_transpired, vesting_months):
    verify_vesting_remaining_factor(vesting_months, months_transpired)


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

    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))
    with patch.object(maya, 'now', return_value=future_date):
        supply_information = calculate_supply_information(economics)
        verify_supply_information(supply_information, max_supply, initial_supply_with_rewards,
                                  worklock_supply, future_date)


def verify_vesting_remaining_factor(vesting_months: int, months_transpired: int):
    future_date = LAUNCH_DATE.add(days=round(months_transpired * DAYS_PER_MONTH))

    # cliff check
    factor = vesting_remaining_factor(vesting_months=vesting_months, cliff=True, now=future_date)
    assert factor == (1 if months_transpired < vesting_months else 0)  # 1 if not yet vested, 0 otherwise

    # non-cliff check
    factor = vesting_remaining_factor(vesting_months=vesting_months, cliff=False, now=future_date)
    assert factor == ((vesting_months - months_transpired)/vesting_months if months_transpired < vesting_months else 0)


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

    ecosystem_supply = INITIAL_SUPPLY - total_locked - saft1_supply - CASI_SUPPLY
    assert supply_information['initial_supply']['unlocked_allocations']['ecosystem'] == str(round(ecosystem_supply, 2))

    total_unlocked = saft1_supply + CASI_SUPPLY + ecosystem_supply

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
