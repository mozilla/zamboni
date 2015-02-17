#!/bin/bash

TARGET="/tmp/elasticsearch"

if [ ! -f "$TARGET/elasticsearch-1.3.8/bin/elasticsearch" ]; then
    echo "$TARGET not found.  Building..."
    pushd $TARGET
    wget https://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-1.3.8.tar.gz
    tar xvf elasticsearch-1.3.8.tar.gz
    elasticsearch-1.3.8/bin/plugin -install elasticsearch/elasticsearch-analysis-icu/2.3.0
else
    echo "$TARGET already exists"
fi
