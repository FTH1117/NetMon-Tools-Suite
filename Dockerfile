# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Use a build argument to conditionally copy the 'almalinux' directory
ARG INCLUDE_ALMALINUX=false

# If INCLUDE_ALMALINUX is true, copy 'almalinux' into /home/almalinux
RUN if [ "$INCLUDE_ALMALINUX" = "true" ] ; then \
      mkdir -p /home/almalinux && \
      cp -r /app/almalinux/* /home/almalinux/ ; \
    fi

# Create the log directory
RUN mkdir -p /var/log/app

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose the port that the app runs on
EXPOSE 5000

# Command to run the Flask app
CMD ["python3", "web_app/app.py"]
