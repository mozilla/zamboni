#!/bin/bash

TARGET="/tmp/elasticsearch"

if [ ! -f "$TARGET/elasticsearch-1.2.4/bin/elasticsearch" ]; then
    echo "$TARGET not found.  Building..."
    pushd $TARGET
    wget https://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-1.2.4.tar.gz
    tar xvf elasticsearch-1.2.4.tar.gz
    elasticsearch-1.2.4/bin/plugin -install elasticsearch/elasticsearch-analysis-icu/2.2.0
else
    echo "$TARGET already exists"
fi
