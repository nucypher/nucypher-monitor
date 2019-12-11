![](nucypher.png)

# NuCypher Monitor

The NuCypher Monitor collects data about the [NuCypher Network](https://github.com/nucypher/nucypher) via the `Crawler`
and displays this information in a UI via the `Dashboard`.


### Installation

```bash
$ pip install -e . -r requirements.txt
```

##### Install additional development packages
```bash
$ pip install -e . -r dev-requirements.txt
```

### Minimum Requirements
* Installation of [InfluxDB](https://www.influxdata.com/)

    The Monitor `Crawler` stores network blockchain information in an `InfluxDB` time-series instance. The default connection
is made to a local instance.

* Installation of Geth Ethereum Node

    The Monitor needs a Web3 node provider to obtain blockchain data.


### Usage
```bash
$ nucypher-monitor --help
Usage: nucypher-monitor [OPTIONS] COMMAND [ARGS]...

Options:
  --nucypher-version  Echo the nucypher version
  --help              Show this message and exit.

Commands:
  crawl      Gather NuCypher network information.
  dashboard  Run UI dashboard of NuCypher network.
```

### Running the Monitor

#### via CLI

1. Run InfluxDB
```bash
$ sudo influxd
```

2. Run Geth node as a Web3 node provider (or use Infura)
```bash
$ geth --goerli --nousb
```

3. Run the `Crawler`
```bash
$ nucypher-monitor crawl --provider <YOUR_WEB3_PROVIDER_URI>
```

4. Run the `Dashboard`
```bash
$ nucypher-monitor dashboard --provider <YOUR WEB3 PROVIDER URI>
```

5. The `Dashboard` UI is available at https://127.0.0.1:12500.


#### via Docker Compose

Docker Compose will start InfluxDB, Crawler, and Dashboard containers, and no installation of the monitor is required.

1. Set Web3 Provider URI environment variable

    **NOTE: local ipc is not supported when running via Docker**

```bash
export WEB3_PROVIDER_URI=<YOUR WEB3 PROVIDER URI>
```

2. Run Docker Compose
```bash
docker-compose -f deploy/docker-compose.yml up
```
