# NetMon Tools Suite

## Overview
The NetMon Tools Suite is a comprehensive toolkit designed to automate and streamline network monitoring and management processes. It integrates Zabbix and Grafana to provide real-time data visualization and performance tracking, alongside tools for automated reporting, ticket management using Supportpal, and project control through a user-friendly web interface.

## Features
- **Zabbix Integration**: Automate fetching and visualization of Zabbix monitoring data.
- **Grafana Dashboard Management**: Create and manage Grafana dashboards dynamically for in-depth analytics.
- **Automated Reporting**: Generate detailed performance reports automatically.
- **Ticket Fetching**: Automate ticket fetching and compilation for efficient management.
- **Web Interface**: Manage projects, graph exports, and reports through a Flask-based web application.
- **Connection Testing**: Ensure and test network connectivity and reliability.

## Prerequisites
Ensure your system has the following software installed:
- Python 3.8 or later
- Flask
- Requests
- python-docx
- Gunicorn
- Werkzeug
- Pillow

Install all the required packages using:
```bash
pip install -r requirements.txt
```
## Configuration
Configure your Zabbix, Grafana API and Supportpal details and other parameters by editing the configuration files in the config/ directory according to your setup needs.

## Usage
To launch the Flask web application and access the web interface:
```bash
python app.py
```
Access the web interface at http://localhost:5000 to manage projects, export graphs, and generate reports effectively.
