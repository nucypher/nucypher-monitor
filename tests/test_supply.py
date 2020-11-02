from collections import OrderedDict
from typing import Dict
from unittest.mock import MagicMock, patch

import maya
import pytest
from maya import MayaDT
from nucypher.blockchain.eth.token import NU

from monitor.supply import LAUNCH_DATE, vesting_remaining_factor, DAYS_PER_MONTH, calculate_supply_information, \
    INITIAL_SUPPLY, UNIVERSITY_INITIAL_SUPPLY, CASI_SUPPLY, months_transpired_since_launch, SAFT2_INITIAL_SUPPLY, \
    TEAM_INITIAL_SUPPLY, NUCO_INITIAL_SUPPLY, SAFT1_SUPPLY, NUCO_VESTING_MONTHS, WORKLOCK_VESTING_MONTHS, \
    UNIVERSITY_VESTING_MONTHS, SAFT2_TEAM_VESTING_MONTHS

TEST_REWARDS_PER_MONTH = NU(83_333, 'NU')


def test_months_transpired():
    # ensure months transpired match calculation used for locked periods for allocations
    max_locked_months = 5*12  # 5 years of time
    for i in range(1, max_locked_months+1):
        lock_periods_used_in_allocation = round(i * DAYS_PER_MONTH)  # calculation used in allocations
        months_transpired = months_transpired_since_launch(LAUNCH_DATE.add(days=lock_periods_used_in_allocation))
        # ensure that calculation of months matches calculation used for locked periods
        assert months_transpired == i, f"{i} months transpired"


def test_months_transpired_rounding_days():
    # ensure months transpired match calculation used for locked periods for allocations
    max_locked_months = 5*12  # 5 years of time
    for i in range(1, max_locked_months+1):
        for j in range(1, 30):
            # each day within month
            lock_periods_used_in_allocation = round(i * DAYS_PER_MONTH) + j  # calculation used in allocations
            months_transpired = months_transpired_since_launch(LAUNCH_DATE.add(days=lock_periods_used_in_allocation))
            # ensure that calculation of months matches calculation used for locked periods
            assert months_transpired == i, f"{i} months {j} days transpired"


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


def test_supply_information_at_launch():
    launch_result = OrderedDict({
        "initial_supply": {
            "total_allocated": 1000000000,
            "locked_allocations": {
                "saft2": 80000000,
                "team": 106000000,
                "company": 200000000,
                "worklock": 225000000,
                "university": 19500000
            },
            "unlocked_allocations": {
                "saft1": 319000000,
                "casi": 9000000,
                "vested": 0,
                "ecosystem": 41500000
            }
        },
        "staking_rewards_supply": {
            "total_allocated": 2885390081.75,
            "staking_rewards_issued": 0,
            "staking_rewards_remaining": 2885390081.75
        },
        "max_supply": 3885390081.75,
        "current_total_supply": 1000000000,
        "est_circulating_supply": 369500000
    })

    # initial values
    max_supply = NU(3885390081.748248632541961138, 'NU')
    worklock_supply = NU(225_000_000, 'NU')

    economics = MagicMock(total_supply=max_supply.to_nunits(),
                          worklock_supply=worklock_supply.to_nunits(),
                          initial_supply=INITIAL_SUPPLY.to_nunits())

    with patch.object(maya, 'now', return_value=LAUNCH_DATE):
        supply_information = calculate_supply_information(economics)
        assert supply_information == launch_result  # order matters


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
    assert supply_information['initial_supply']['total_allocated'] == float(round(INITIAL_SUPPLY, 2).to_tokens())

    # Locked
    vest_24_months = vesting_remaining_factor(vesting_months=24, cliff=False, now=future_date)
    vest_6_months_cliff = vesting_remaining_factor(vesting_months=6, cliff=True, now=future_date)
    vest_3_years_cliff = vesting_remaining_factor(vesting_months=3*12, cliff=True, now=future_date)
    vest_5_years_cliff = vesting_remaining_factor(vesting_months=5*12, cliff=True, now=future_date)

    vested_nu = NU(0, 'NU')

    saft2_supply = NU(value=(SAFT2_INITIAL_SUPPLY.to_nunits() * vest_24_months),
                      denomination='NuNit')
    assert (supply_information['initial_supply']['locked_allocations']['saft2'] ==
            float(round(saft2_supply, 2).to_tokens()))
    vested_nu += SAFT2_INITIAL_SUPPLY - saft2_supply

    team_supply = NU(value=(TEAM_INITIAL_SUPPLY.to_nunits() * vest_24_months),
                     denomination='NuNit')
    assert (supply_information['initial_supply']['locked_allocations']['team'] ==
            float(round(team_supply, 2).to_tokens()))
    vested_nu += TEAM_INITIAL_SUPPLY - team_supply

    nuco_supply = NU(value=(NUCO_INITIAL_SUPPLY.to_nunits() * vest_5_years_cliff),
                     denomination='NuNit')
    assert (supply_information['initial_supply']['locked_allocations']['company'] ==
            float(round(nuco_supply, 2).to_tokens()))
    vested_nu += NUCO_INITIAL_SUPPLY - nuco_supply

    wl_supply = NU(value=(worklock_supply.to_nunits() * vest_6_months_cliff), denomination='NuNit')
    assert (supply_information['initial_supply']['locked_allocations']['worklock'] ==
            float(round(wl_supply, 2).to_tokens()))
    vested_nu += worklock_supply - wl_supply

    university_supply = NU(value=(UNIVERSITY_INITIAL_SUPPLY.to_nunits() * vest_3_years_cliff), denomination='NuNit')
    assert (supply_information['initial_supply']['locked_allocations']['university'] ==
            float(round(university_supply, 2).to_tokens()))
    vested_nu += UNIVERSITY_INITIAL_SUPPLY - university_supply

    total_locked = saft2_supply + team_supply + nuco_supply + wl_supply + university_supply

    # Unlocked
    assert (supply_information['initial_supply']['unlocked_allocations']['saft1'] ==
            float(round(SAFT1_SUPPLY, 2).to_tokens()))

    assert (supply_information['initial_supply']['unlocked_allocations']['casi'] ==
            float(round(CASI_SUPPLY, 2).to_tokens()))

    months_transpired = months_transpired_since_launch(now=future_date)

    vesting_times_and_amounts = OrderedDict({
        WORKLOCK_VESTING_MONTHS: worklock_supply,
        SAFT2_TEAM_VESTING_MONTHS: (SAFT2_INITIAL_SUPPLY + TEAM_INITIAL_SUPPLY),
        UNIVERSITY_VESTING_MONTHS: UNIVERSITY_INITIAL_SUPPLY,
        NUCO_VESTING_MONTHS: NUCO_INITIAL_SUPPLY,
    })
    if months_transpired > min(NUCO_VESTING_MONTHS, WORKLOCK_VESTING_MONTHS,
                               UNIVERSITY_VESTING_MONTHS, SAFT2_TEAM_VESTING_MONTHS):
        vested_total = NU(0, 'NU')
        for vesting_months, vesting_value in vesting_times_and_amounts.items():
            if months_transpired > vesting_months:
                assert vested_nu >= vesting_value  # >= vesting amount (redundant but meh)
                vested_total += vesting_value
                assert vested_nu >= vested_total  # >= vesting total

    assert (supply_information['initial_supply']['unlocked_allocations']['vested'] ==
            float(round(vested_nu, 2).to_tokens()))

    ecosystem_supply = INITIAL_SUPPLY - total_locked - SAFT1_SUPPLY - CASI_SUPPLY - vested_nu
    assert (supply_information['initial_supply']['unlocked_allocations']['ecosystem'] ==
            float(round(ecosystem_supply, 2).to_tokens()))

    total_unlocked = SAFT1_SUPPLY + CASI_SUPPLY + vested_nu + ecosystem_supply

    # Staking Rewards
    assert (supply_information['staking_rewards_supply']['total_allocated'] ==
            float(round(max_supply - INITIAL_SUPPLY, 2).to_tokens()))
    assert (supply_information['staking_rewards_supply']['staking_rewards_issued'] ==
            float(round(initial_supply_with_rewards - INITIAL_SUPPLY, 2).to_tokens()))
    assert (supply_information['staking_rewards_supply']['staking_rewards_remaining'] ==
            float(round(max_supply - initial_supply_with_rewards, 2).to_tokens()))

    # Max Supply
    assert supply_information['max_supply'] == float(round(max_supply, 2).to_tokens())

    # Circulating Supply
    assert supply_information['est_circulating_supply'] == float(round(total_unlocked, 2).to_tokens())
