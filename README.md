![alt text](docs/IBC-logo.jpg)
![alt text](docs/eu.png)

# iBeChange Digital Twin
[![License: CC-BY-4.0-International](https://img.shields.io/badge/License-CC%20BY%204.0-blue.svg)](#license)

# Data model

![data-model](docs/data_model.svg)


# Deploy

```bash
docker volume create metabase_data
docker compose up --build -d
docker compose logs app
docker compose down
```
