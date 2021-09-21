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
+* Ethereum Node - either local or remote

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

1. Use remote Ethereum node provider e.g. Infura, Alchemy etc., OR run local Geth node

2. Run the `Crawler`
    
```bash
$ nucypher-monitor crawl --provider <YOUR_WEB3_PROVIDER_URI> --network <NETWORK NAME>

|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= Crawler =========

Network: <NETWORK NAME>
Provider: ...
Refresh Rate: 60s
Running Nucypher Crawler JSON endpoint at http://localhost:9555/stats
```

3. Run the `Dashboard`
    
```bash

$ nucypher-monitor dashboard --provider <YOUR WEB3 PROVIDER URI> --network <NETWORK NAME>

 _____         _ _           
|     |___ ___|_| |_ ___ ___ 
| | | | . |   | |  _| . |  _|
|_|_|_|___|_|_|_|_| |___|_|  

========= Dashboard =========

Network: <NETWORK NAME>
Crawler: localhost:9555
Provider: ...
Running Monitor Dashboard - https://127.0.0.1:12500


```

4. The `Dashboard` UI is available at https://127.0.0.1:12500.

    **NOTE: The UI will remain empty until after the crawler has collected data during its first scraping round**


#### via Docker Compose

Docker Compose will start the Crawler and Dashboard containers, and no installation of the monitor is required.

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

     **NOTE: The UI will remain empty until after the crawler has collected data during its first scraping round**
