#!/bin/bash

printf -v i "%03d" $1

curl --form addressFile=@addresses-13-$i.csv --form benchmark=9 https://geocoding.geo.census.gov/geocoder/locations/addressbatch --output addresses-13-$i-out.csv
