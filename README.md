![alt text](docs/IBC-logo.jpg)
![alt text](docs/eu.png)

# iBeChange Digital Twin

# Data model

![data-model](docs/data_model.svg)

# Deploy

```bash
docker volume create metabase_data
docker compose up --build -d
docker compose logs app
docker compose down
```
