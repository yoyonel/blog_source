#!/bin/bash

cd pelican
make publish
cd ..

rm -fR deploy/*
cp -R pelican/output/* deploy/
