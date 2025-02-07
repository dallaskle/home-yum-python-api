Step 1: Build the Docker image

docker buildx build --platform linux/amd64 -t dallasklein/home-yum-python-api:latest .

Step 2: Push the Docker image to Docker Hub

docker push dallasklein/home-yum-python-api:latest