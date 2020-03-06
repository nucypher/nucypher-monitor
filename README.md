![](nucypher.png)

# NuCypher Monitor

The NuCypher Monitor collects data about the [NuCypher Network](https://github.com/nucypher/nucypher) via the `Crawler`
and displays this information in a UI via the `Dashboard`.


### Standard Installation

```bash
$ pip install . -r requirements.txt
```

##### Development Installation
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


 8888888           .d888 888                   8888888b.  888888b.
   888            d88P"  888                   888  "Y88b 888  "88b
   888            888    888                   888    888 888  .88P
   888   88888b.  888888 888 888  888 888  888 888    888 8888888K.
   888   888 "88b 888    888 888  888  Y8bd8P' 888    888 888  "Y88b
   888   888  888 888    888 888  888   X88K   888    888 888    888
   888   888  888 888    888 Y88b 888 .d8""8b. 888  .d88P 888   d88P
 8888888 888  888 888    888  "Y88888 888  888 8888888P"  8888888P"

2020-01-29T19:07:09.671836Z	info	InfluxDB starting	{"log_id": "0Kdg2Tul000", "version": "1.7.8", "branch": "1.7", "commit": "ff383cdc0420217e3460dabe17db54f8557d95b6"}
...

```

2. Run Geth node as a Web3 node provider (or use Infura)
```bash
$ geth --goerli --nousb

INFO [01-29|11:06:06.816] Maximum peer count                       ETH=50 LES=0 total=50
...
INFO [01-29|11:06:09.046] Started P2P networking                   self=enode://1eb7c99106888c206583abc63fc58da1c202965b32486115575d27e03aba0e0c1be433f0a7060da3ecc95afbbce845a7d3df703307d94fe328602c3d105daf36@127.0.0.1:30303
INFO [01-29|11:06:09.048] IPC endpoint opened                      url=/home/k/.ethereum/goerli/geth.ipc
```

3. Run the `Crawler`

    **NOTE: If using a POA network, e.g. Goerli, then the `--poa` flag should be specified**
    
```bash
$ nucypher-monitor crawl --provider <YOUR_WEB3_PROVIDER_URI> --network <NETWORK NAME>

|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= Crawler =========

Connecting to preferred teacher nodes...
Network: Cassandra
InfluxDB: 0.0.0.0:8086
Provider: ...
Refresh Rate: 60s
Running Nucypher Crawler JSON endpoint at http://localhost:9555/stats
```

4. Run the `Dashboard`

    **NOTE: If using a POA network, e.g. Goerli, then the `--poa` flag should be specified**
    
```bash

$ nucypher-monitor dashboard --provider <YOUR WEB3 PROVIDER URI> --network <NETWORK NAME>

 _____         _ _           
|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= Dashboard =========

Network: Cassandra
Crawler: localhost:9555
InfluxDB: localhost:8086
Provider: ...
Running Monitor Dashboard - https://127.0.0.1:12500


```

5. The `Dashboard` UI is available at https://127.0.0.1:12500.


#### via Docker Compose

Docker Compose will start InfluxDB, Crawler, and Dashboard containers, and no installation of the monitor is required.

1. Set required environment variables

* Web3 Provider URI environment variable

    **NOTE: local ipc is not supported when running via Docker**

```bash
export WEB3_PROVIDER_URI=<YOUR WEB3 PROVIDER URI>
```

* Network Name environment variable
```bash
export NUCYPHER_NETWORK=<NETWORK NAME>
```

2. Run Docker Compose
```bash
docker-compose -f deploy/docker-compose.yml up
```

Alternatively, you can run the services individually
```bash
docker-compose -f deploy/docker-compose.yml up -d influxdb
docker-compose -f deploy/docker-compose.yml up -d crawler
docker-compose -f deploy/docker-compose.yml up -d web
```

**NOTE: If the `--poa` flag is required, the services should be run individually, and the `--poa` flag appended to the `crawler` and `web` commands**

3. View Docker compose logs
```bash
docker-compose -f deploy/docker-compose.yml logs -f
```

Alternatively, to view logs for a specific service
```bash
docker-compose -f deploy/docker-compose.yml logs -f <SERVICE_NAME>
```

4. The `Dashboard` UI is available on port 12500.
