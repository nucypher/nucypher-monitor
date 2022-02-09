import math
from collections import OrderedDict
from typing import Union, Optional, Dict

import maya
from maya import MayaDT
from nucypher.blockchain.eth.token import NU

SAFT1_ALLOCATION_PERCENTAGE = 0.319
SAFT2_ALLOCATION_PERCENTAGE = 0.08
TEAM_ALLOCATION_PERCENTAGE = 0.106
NUCO_ALLOCATION_PERCENTAGE = 0.2

INITIAL_SUPPLY = NU(1_000_000_000, 'NU')

UNIVERSITY_INITIAL_SUPPLY = NU(19_500_000, 'NU')
SAFT2_INITIAL_SUPPLY = NU(value=(SAFT2_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits()), denomination='NuNit')
TEAM_INITIAL_SUPPLY = NU(value=(TEAM_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits()), denomination='NuNit')
NUCO_INITIAL_SUPPLY = NU(value=(NUCO_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits()), denomination='NuNit')

SAFT1_SUPPLY = NU(value=(SAFT1_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits()), denomination='NuNit')
CASI_SUPPLY = NU(9_000_000, 'NU')

NUCO_VESTING_MONTHS = 5 * 12
WORKLOCK_VESTING_MONTHS = 6
UNIVERSITY_VESTING_MONTHS = 3 * 12
SAFT2_TEAM_VESTING_MONTHS = 24

LAUNCH_DATE = MayaDT.from_rfc3339('2020-10-15T00:00:00.0Z')
DAYS_PER_MONTH = 30.416  # value used in csv allocations


def months_transpired_since_launch(now: MayaDT) -> int:
    """
    Determines the number of months transpired since the launch date, Oct 15, 2020 00:00:00 UTC, based on how
    monthly durations were calculated when allocations were distributed.
    """
    days_transpired = (now - LAUNCH_DATE).days
    months_transpired = days_transpired / DAYS_PER_MONTH

    months_transpired_ceil = math.ceil(months_transpired)
    # calculation of vesting days (based on months) done during allocation
    rounded_up_months_min_duration_days = round(months_transpired_ceil * DAYS_PER_MONTH)

    if rounded_up_months_min_duration_days <= days_transpired:
        return months_transpired_ceil
    else:
        # required days not yet surpassed for subsequent month - use floor value
        return math.floor(months_transpired)


def vesting_remaining_factor(vesting_months: int,
                             cliff: bool = False,
                             now: Optional[MayaDT] = None) -> Union[float, int]:
    """
    Calculates the remaining percentage of tokens that should still be locked relative to launch date,
    Oct 15, 2020 00:00:00 UTC, based on the provided vesting characteristics.
    """
    if not now:
        now = maya.now()

    months_transpired = months_transpired_since_launch(now)
    if cliff:
        return 1 if months_transpired < vesting_months else 0
    else:
        if months_transpired >= vesting_months:
            # vesting period fully completed
            return 0
        else:
            return (vesting_months - months_transpired) / vesting_months


def calculate_supply_information(max_supply: NU,
                                 current_total_supply: NU,
                                 worklock_supply: NU,
                                 now: Optional[MayaDT] = None) -> Dict:
    """Calculates the NU token supply information."""
    supply_info = OrderedDict()
    initial_supply_with_rewards = current_total_supply

    # Initial Supply Information
    initial_supply_info = OrderedDict()
    supply_info['initial_supply'] = initial_supply_info
    initial_supply_info['total_allocated'] = float(INITIAL_SUPPLY.to_tokens())

    # - Locked allocations
    locked_allocations = OrderedDict()
    initial_supply_info['locked_allocations'] = locked_allocations
    if not now:
        now = maya.now()

    vest_saft2_team_factor = vesting_remaining_factor(vesting_months=SAFT2_TEAM_VESTING_MONTHS, cliff=False, now=now)
    vest_worklock_factor = vesting_remaining_factor(vesting_months=WORKLOCK_VESTING_MONTHS, cliff=True, now=now)
    vest_nuco_factor = vesting_remaining_factor(vesting_months=NUCO_VESTING_MONTHS, cliff=True, now=now)
    vest_university_factor = vesting_remaining_factor(vesting_months=UNIVERSITY_VESTING_MONTHS, cliff=True, now=now)
    vested_nu = NU(0, 'NU')

    saft2_locked_supply = NU(value=(SAFT2_INITIAL_SUPPLY.to_nunits() * vest_saft2_team_factor), denomination='NuNit')
    vested_nu += (SAFT2_INITIAL_SUPPLY - saft2_locked_supply)

    team_locked_supply = NU(value=(TEAM_INITIAL_SUPPLY.to_nunits() * vest_saft2_team_factor), denomination='NuNit')
    vested_nu += (TEAM_INITIAL_SUPPLY - team_locked_supply)

    nuco_locked_supply = NU(value=(NUCO_INITIAL_SUPPLY.to_nunits() * vest_nuco_factor), denomination='NuNit')
    vested_nu += (NUCO_INITIAL_SUPPLY - nuco_locked_supply)

    worklock_locked_supply = NU(value=(worklock_supply.to_nunits() * vest_worklock_factor), denomination='NuNit')
    vested_nu += (worklock_supply - worklock_locked_supply)

    university_locked_supply = NU(value=(UNIVERSITY_INITIAL_SUPPLY.to_nunits() * vest_university_factor),
                                  denomination='NuNit')
    vested_nu += (UNIVERSITY_INITIAL_SUPPLY - university_locked_supply)

    locked_allocations['saft2'] = float(saft2_locked_supply.to_tokens())
    locked_allocations['team'] = float(team_locked_supply.to_tokens())
    locked_allocations['company'] = float(nuco_locked_supply.to_tokens())
    locked_allocations['worklock'] = float(worklock_locked_supply.to_tokens())
    locked_allocations['university'] = float(university_locked_supply.to_tokens())

    total_locked_allocations = (saft2_locked_supply + team_locked_supply + nuco_locked_supply +
                                worklock_locked_supply + university_locked_supply)

    # - Unlocked Allocations
    unlocked_supply_info = OrderedDict()
    initial_supply_info['unlocked_allocations'] = unlocked_supply_info
    unlocked_supply_info['saft1'] = float(SAFT1_SUPPLY.to_tokens())
    unlocked_supply_info['casi'] = float(CASI_SUPPLY.to_tokens())
    unlocked_supply_info['vested'] = float(vested_nu.to_tokens())
    ecosystem_supply = INITIAL_SUPPLY - total_locked_allocations - (SAFT1_SUPPLY + CASI_SUPPLY + vested_nu)
    unlocked_supply_info['ecosystem'] = float(ecosystem_supply.to_tokens())

    total_unlocked_allocations = SAFT1_SUPPLY + CASI_SUPPLY + vested_nu + ecosystem_supply

    # Staking Rewards Information
    staking_rewards_info = OrderedDict()
    supply_info['staking_rewards_supply'] = staking_rewards_info
    staking_rewards_remaining = max_supply - initial_supply_with_rewards
    staking_rewards_issued = initial_supply_with_rewards - INITIAL_SUPPLY
    staking_rewards_total_allocated = staking_rewards_remaining + staking_rewards_issued
    staking_rewards_info['total_allocated'] = float(staking_rewards_total_allocated.to_tokens())
    staking_rewards_info['staking_rewards_issued'] = float(staking_rewards_issued.to_tokens())
    staking_rewards_info['staking_rewards_remaining'] = float(staking_rewards_remaining.to_tokens())

    # Max Supply
    supply_info['max_supply'] = float(max_supply.to_tokens())

    # Current Total Supply
    supply_info['current_total_supply'] = float(initial_supply_with_rewards.to_tokens())

    # Est. Circulating Supply = total unlocked + rewards
    est_circulating_supply = total_unlocked_allocations + staking_rewards_issued
    supply_info['est_circulating_supply'] = float(est_circulating_supply.to_tokens())
    return supply_info

