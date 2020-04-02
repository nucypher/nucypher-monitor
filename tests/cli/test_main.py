from unittest.mock import MagicMock, patch

import nucypher
import pytest
from click.testing import CliRunner
from nucypher.blockchain.eth.agents import StakingEscrowAgent

import monitor
from monitor.cli.main import monitor as monitor_cli, CRAWLER, MONITOR_BANNER, DASHBOARD
from tests.utilities import MockContractAgency


@pytest.fixture(scope='module')
def click_runner():
    runner = CliRunner()
    yield runner


def test_monitor_echo_nucypher_version(click_runner):
    version_args = ('--nucypher-version', )
    result = click_runner.invoke(monitor_cli, version_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(nucypher.__version__) in result.output, f"nucypher version displayed"


def test_monitor_help_message(click_runner):
    help_args = ('--help', )
    result = click_runner.invoke(monitor_cli, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert f'{monitor_cli.name} [OPTIONS] COMMAND [ARGS]' in result.output, 'Missing or invalid help text was produced.'
    for sub_command in monitor_cli.commands.values():
        assert sub_command.name in result.output, f"Sub command {sub_command.name} in help message"


@pytest.mark.parametrize('command_name, command', ([command.name, command] for command in monitor_cli.commands.values()))
def test_monitor_sub_command_help_messages(click_runner, command_name, command):
    result = click_runner.invoke(monitor_cli, (command_name, '--help'), catch_exceptions=False)
    assert result.exit_code == 0
    assert f'{monitor_cli.name} {command_name} [OPTIONS]' in result.output, \
        f"Sub command {command_name} has valid help text."


# TODO fix test
@pytest.mark.skip('not working')
def test_monitor_crawl_run(click_runner):
    crawl_args = ('crawl', '--dry-run', '--provider', 'tester://pyevm')
    result = click_runner.invoke(monitor_cli, crawl_args, catch_exceptions=False)
    assert MONITOR_BANNER.format(CRAWLER) in result.output
    assert result.exit_code == 0


# TODO fix test
@pytest.mark.skip('not working')
@patch('monitor.dashboard.CrawlerInfluxClient', autospec=True)
@patch.object(monitor.dashboard.ContractAgency, 'get_agent', autospec=True)
@patch.object(monitor.cli.main.BlockchainInterfaceFactory, 'initialize_interface', autospec=True)
def test_monitor_dashboard_run(init_interface, get_agent, click_runner):
    # mock BlockchainInterfaceFactory
    init_interface.return_value = MagicMock()

    # mock StakingEscrowAgent and ContractAgency
    staking_agent = MagicMock(spec=StakingEscrowAgent)
    contract_agency = MockContractAgency(staking_agent=staking_agent)
    get_agent.side_effect = contract_agency.get_agent

    dashboard_args = ('dashboard',
                      '--dry-run')
    result = click_runner.invoke(monitor_cli, dashboard_args, catch_exceptions=False)
    assert MONITOR_BANNER.format(DASHBOARD) in result.output
    assert result.exit_code == 0
