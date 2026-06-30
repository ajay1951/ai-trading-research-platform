@echo off
echo [+] Starting Native InfluxDB Import...

REM We use docker exec to run the native influx CLI inside the container
REM The container has /data mounted to the Windows data/ folder.

docker exec influxdb influx write -o quant_fund -b crypto_mtf -f /data/influx_seed.lp

echo [+] Import Complete!
