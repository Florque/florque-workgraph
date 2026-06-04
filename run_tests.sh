#!/bin/bash
set -e

# --- Configuration ---
VENV_DIR="venv"
MEMGRAPH_CONTAINER_NAME="memgraph-test"
MEMGRAPH_PORT=7666
MEMGRAPH_IMAGE="memgraph/memgraph"

# --- Functions ---
function cleanup {
    echo "Cleaning up..."
    if [ "$(docker ps -q -f name=$MEMGRAPH_CONTAINER_NAME)" ]; then
        echo "Stopping Memgraph container..."
        docker stop $MEMGRAPH_CONTAINER_NAME
    fi
}

# --- Main Script ---

# Ensure cleanup runs on script exit
trap cleanup EXIT

# 1. Setup Virtual Environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv $VENV_DIR
fi

echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# 2. Install Dependencies
echo "Installing dependencies..."
pip install -e ".[test]"

# 3. Start Memgraph Container
echo "Setting up Memgraph container..."
if [ "$(docker ps -a -q -f name=$MEMGRAPH_CONTAINER_NAME)" ]; then
    echo "Removing existing Memgraph container..."
    docker rm -f $MEMGRAPH_CONTAINER_NAME
fi

echo "Starting new Memgraph container..."
docker run -d --name $MEMGRAPH_CONTAINER_NAME -p $MEMGRAPH_PORT:7687 --rm $MEMGRAPH_IMAGE

# Add a small delay to ensure Memgraph is ready
sleep 5

# 4. Run Tests
echo "Running tests..."
pytest tests/

echo "Tests finished successfully."
