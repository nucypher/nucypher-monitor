from collections import OrderedDict
from typing import Union, Optional, Dict

import maya
from maya import MayaDT
from nucypher.blockchain.economics import BaseEconomics
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
    return round((now - LAUNCH_DATE).days / DAYS_PER_MONTH)


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


def calculate_supply_information(economics: BaseEconomics) -> Dict:
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

    worklock_locked_supply = NU(value=(economics.worklock_supply * vest_worklock_factor), denomination='NuNit')
    vested_nu += NU(value=(economics.worklock_supply - worklock_locked_supply.to_nunits()), denomination='NuNit')

    university_locked_supply = NU(value=(UNIVERSITY_INITIAL_SUPPLY.to_nunits() * vest_university_factor),
                                  denomination='NuNit')
    vested_nu += (UNIVERSITY_INITIAL_SUPPLY - university_locked_supply)

    locked_allocations['saft2'] = str(round(saft2_locked_supply, 2))
    locked_allocations['team'] = str(round(team_locked_supply, 2))
    locked_allocations['company'] = str(round(nuco_locked_supply, 2))
    locked_allocations['worklock'] = str(round(worklock_locked_supply, 2))
    locked_allocations['university'] = str(round(university_locked_supply, 2))

    total_locked_allocations = (saft2_locked_supply + team_locked_supply + nuco_locked_supply +
                                worklock_locked_supply + university_locked_supply)

    # - Unlocked Allocations
    unlocked_supply_info = OrderedDict()
    initial_supply_info['unlocked_allocations'] = unlocked_supply_info
    unlocked_supply_info['saft1'] = str(round(SAFT1_SUPPLY, 2))
    unlocked_supply_info['casi'] = str(round(CASI_SUPPLY, 2))
    unlocked_supply_info['vested'] = str(round(vested_nu, 2))
    ecosystem_supply = INITIAL_SUPPLY - total_locked_allocations - (SAFT1_SUPPLY + CASI_SUPPLY + vested_nu)
    unlocked_supply_info['ecosystem'] = str(round(ecosystem_supply, 2))

    total_unlocked_allocations = SAFT1_SUPPLY + CASI_SUPPLY + vested_nu + ecosystem_supply

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
