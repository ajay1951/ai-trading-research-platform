@echo off
echo [+] Starting Institutional InfluxDB Server...
docker run -d -p 8086:8086 ^
  --name influxdb ^
  -v "%cd%\influxdb2:/var/lib/influxdb2" ^
  -v "%cd%\data:/data" ^
  -e DOCKER_INFLUXDB_INIT_MODE=setup ^
  -e DOCKER_INFLUXDB_INIT_USERNAME=admin ^
  -e DOCKER_INFLUXDB_INIT_PASSWORD=adminpassword ^
  -e DOCKER_INFLUXDB_INIT_ORG=quant_fund ^
  -e DOCKER_INFLUXDB_INIT_BUCKET=crypto_mtf ^
  -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=institutional_super_secret_token_2026 ^
  influxdb:2.7
echo [+] InfluxDB is running on http://localhost:8086
