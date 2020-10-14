#!/bin/bash

echo "message 1"

sleep 1

>&2 echo "error 1"

sleep 1

echo "message 2"

sleep 1

>&2 echo "error 2"

echo -n "var x: "
read var_x
echo "${var_x}"

