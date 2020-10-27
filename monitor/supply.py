import math
from collections import OrderedDict
from typing import Union, Optional

import maya
from maya import MayaDT
from nucypher.blockchain.economics import BaseEconomics
from nucypher.blockchain.eth.token import NU

INITIAL_SUPPLY = NU(1_000_000_000, 'NU')
UNIVERSITY_SUPPLY = NU(19_500_000, 'NU')
CASI_SUPPLY = NU(8_280_000, 'NU')  # TODO is this correct?

SAFT1_ALLOCATION_PERCENTAGE = 0.319
SAFT2_ALLOCATION_PERCENTAGE = 0.08
TEAM_ALLOCATION_PERCENTAGE = 0.106
NUCO_ALLOCATION_PERCENTAGE = 0.2

NUCO_VESTING_MONTHS = 5 * 12  # TODO is this correct?
WORKLOCK_VESTING_MONTHS = 6
UNIVERSITY_VESTING_MONTHS = 3 * 12

LAUNCH_DATE = MayaDT.from_rfc3339('2020-10-15T00:00:00.0Z')
DAYS_PER_MONTH = 30.416  # value used in allocations


def vesting_remaining_factor(vesting_months: int, cliff: bool = False, now: Optional[MayaDT] = None) -> Union[float, int]:
    """
    Calculates the remaining percentage of tokens that should still be locked relative to launch date,
    Oct 15, 2020 00:00:00 UTC, based on the provided vesting characteristics.
    """
    if not now:
        now = maya.now()

    months_transpired = math.floor((now - LAUNCH_DATE).days / DAYS_PER_MONTH)  # round down
    if cliff:
        return 1 if months_transpired < vesting_months else 0
    else:
        if months_transpired >= vesting_months:
            # vesting period fully completed
            return 0
        else:
            return (vesting_months - months_transpired) / vesting_months


def calculate_supply_information(economics: BaseEconomics):
    """Calculates the NU token supply information."""
    supply_info = OrderedDict()
    max_supply = NU.from_nunits(economics.total_supply)

    # Initial Supply Information
    initial_supply_info = OrderedDict()
    supply_info['initial_supply'] = initial_supply_info
    initial_supply_info['total_allocated'] = str(round(INITIAL_SUPPLY, 2))

    # - Locked allocations
    locked_allocations = OrderedDict()
    initial_supply_info['locked_allocations'] = locked_allocations
    now = maya.now()
    vest_24_month_factor = vesting_remaining_factor(vesting_months=24, cliff=False, now=now)
    vest_worklock_factor = vesting_remaining_factor(vesting_months=WORKLOCK_VESTING_MONTHS, cliff=True, now=now)
    vest_nuco_factor = vesting_remaining_factor(vesting_months=NUCO_VESTING_MONTHS, cliff=True, now=now)
    vest_university_factor = vesting_remaining_factor(vesting_months=UNIVERSITY_VESTING_MONTHS, cliff=True, now=now)
    saft2_supply = NU(value=(SAFT2_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits() * vest_24_month_factor),
                      denomination='NuNit')
    team_supply = NU(value=(TEAM_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits() * vest_24_month_factor),
                     denomination='NuNit')
    nuco_supply = NU(value=(NUCO_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits() * vest_nuco_factor),
                     denomination='NuNit')
    worklock_supply = NU(value=(economics.worklock_supply * vest_worklock_factor), denomination='NuNit')
    university_supply = NU(value=(UNIVERSITY_SUPPLY.to_nunits() * vest_university_factor), denomination='NuNit')

    locked_allocations['saft2'] = str(round(saft2_supply, 2))
    locked_allocations['team'] = str(round(team_supply, 2))
    locked_allocations['company'] = str(round(nuco_supply, 2))
    locked_allocations['worklock'] = str(round(worklock_supply, 2))
    locked_allocations['university'] = str(round(university_supply, 2))

    total_locked_allocations = saft2_supply + team_supply + nuco_supply + worklock_supply + university_supply

    # - Unlocked Allocations
    unlocked_supply_info = OrderedDict()
    initial_supply_info['unlocked_allocations'] = unlocked_supply_info
    saft1_supply = NU(value=(SAFT1_ALLOCATION_PERCENTAGE * INITIAL_SUPPLY.to_nunits()), denomination='NuNit')
    unlocked_supply_info['saft1'] = str(round(saft1_supply, 2))
    unlocked_supply_info['casi'] = str(round(CASI_SUPPLY, 2))
    remaining_unlocked = INITIAL_SUPPLY - total_locked_allocations - (saft1_supply + CASI_SUPPLY)
    unlocked_supply_info['other'] = str(round(remaining_unlocked, 2))

    total_unlocked_allocations = saft1_supply + CASI_SUPPLY + remaining_unlocked

    # Staking Rewards Information
    staking_rewards_info = OrderedDict()
    supply_info['staking_rewards_supply'] = staking_rewards_info
    initial_supply_with_rewards = economics.initial_supply  # economics.initial_supply includes issued rewards
    staking_rewards_remaining = NU.from_nunits(max_supply.to_nunits() - initial_supply_with_rewards)
    staking_rewards_issued = NU.from_nunits(initial_supply_with_rewards - INITIAL_SUPPLY.to_nunits())
    staking_rewards_total_allocated = staking_rewards_remaining + staking_rewards_issued
    staking_rewards_info['total_allocated'] = str(round(staking_rewards_total_allocated, 2))
    staking_rewards_info['staking_rewards_issued'] = str(round(staking_rewards_issued, 2))
    staking_rewards_info['staking_rewards_remaining'] = str(round(staking_rewards_remaining, 2))

    # Max Supply
    supply_info['max_supply'] = str(round(max_supply, 2))

    # Est. Circulating Supply
    supply_info['est_circulating_supply'] = str(round(total_unlocked_allocations, 2))
    return supply_info
