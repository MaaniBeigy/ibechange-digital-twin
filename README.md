# iBeChange Digital Twin

# Data model

[![data-model](docs/data_model.svg)]([docs\data_model.txt](https://raw.githubusercontent.com/MaaniBeigy/ibechange-digital-twin/refs/heads/main/docs/data_model.txt))

# Deploy

```bash
docker volume create metabase_data
docker compose up --build -d
docker compose logs app
docker compose down
```
