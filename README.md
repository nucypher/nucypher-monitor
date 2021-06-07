![](nucypher.png)

# NuCypher Monitor

The NuCypher Monitor collects data about the [NuCypher Network](https://github.com/nucypher/nucypher) via the `Crawler`
and displays this information in a UI via the `Dashboard`.


### Standard Installation

```bash
$ pip install -e . -r requirements.txt
```

##### Development Installation
```bash
$ pip install -e . -r dev-requirements.txt
```

### Minimum Requirements
* Installation of [InfluxDB](https://www.influxdata.com/)

    The Monitor `Crawler` stores network blockchain information in an `InfluxDB` time-series instance. The default connection
is made to a local instance.

* Ethereum Node - either local or remote

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

**NOTE: InfluxDB version must be < 2.0 due to authentication changes made in 2.0+.**

2. Use remote Ethereum node provider e.g. Infura, Alchemy etc., OR run local Geth node

3. Run the `Crawler`
    
```bash
$ nucypher-monitor crawl --provider <YOUR_WEB3_PROVIDER_URI> --network <NETWORK NAME>

|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= Crawler =========

Connecting to preferred teacher nodes...
Network: <NETWORK NAME>
InfluxDB: 0.0.0.0:8086
Provider: ...
Refresh Rate: 60s
Running Nucypher Crawler JSON endpoint at http://localhost:9555/stats
```

4. Run the `Dashboard`
    
```bash

$ nucypher-monitor dashboard --provider <YOUR WEB3 PROVIDER URI> --network <NETWORK NAME>

 _____         _ _           
|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= Dashboard =========

Network: <NETWORK NAME>
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

* Let's Encrypt certificates location
```bash
export NUCYPHER_LETSENCRYPT_DIR=<DIRECTORY LOCATION>
```
You can create certificates for localhost using openssl command:
```
openssl req -x509 -out fullchain.pem -keyout key.pem \
  -newkey rsa:2048 -nodes -sha256 \
  -subj '/CN=localhost' -extensions EXT -config <( \
   printf "[dn]\nCN=localhost\n[req]\ndistinguished_name = dn\n[EXT]\nsubjectAltName=DNS:localhost\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth")
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

3. View Docker compose logs
```bash
docker-compose -f deploy/docker-compose.yml logs -f
```

Alternatively, to view logs for a specific service
```bash
docker-compose -f deploy/docker-compose.yml logs -f <SERVICE_NAME>
```

4. The `Dashboard` UI is available on port 12500.
