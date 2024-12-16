# NetMon Tools Suite

## Overview
The **NetMon Tools Suite** is an integrated monitoring and reporting framework designed to streamline IT infrastructure performance monitoring, SLA tracking, and service availability analysis. It combines Zabbix and Grafana to generate automated monthly reports and includes support for visual insights and predictive analysis using Llama for performance trend evaluations.

## Features
- **Automated Graph Export**: Extract graphs from Zabbix and Grafana for metrics like CPU, Memory, Disk, Network Traffic, and Uptime.
- **Monthly SLA Reporting**: Generate comprehensive SLA reports with performance trends and insights.
- **Integrated Visual Analysis**: Use Llama-based analysis for advanced observations and predictions on performance metrics.
- **Web-Based Management**: Manage projects, reporting tasks, and infrastructure monitoring via a user-friendly Flask web application.
- **Deployment Flexibility**: Choose between CI/CD automation or running the application directly.
- **Network Graph Insights**: Supports exporting network traffic insights for proactive resource allocation.

## Installation
### Prerequisites
- Python 3.8+
- Docker and Docker Compose (optional for CI/CD deployment)
- Zabbix Server with API Access
- Grafana Server with an API Key
- Required Python Libraries (requirements.txt)

### Setup Options
You can choose either **CI/CD Deployment** or **Manual Run** to get started:

### Option 1: CI/CD Deployment

#### 1. Clone the Repository
```bash
git clone <repository-url>
cd NetMon-Tools-Suite
```

#### 2. Configure CI/CD
Update `.gitlab-ci.yml` to include:

- API credentials for Zabbix and Grafana.
- Ensure the CI/CD runner has Docker support.

#### 3. Trigger Deployment
Push the relevant branch to GitLab:

- **For Staging**:
  - Push to the staging branch.

- **For Production**:
  - Push to the main branch.

The CI/CD pipeline will automatically:

- Build the Docker container.
- Deploy the application for the respective environment.

#### 4. Access the Application
- **Production**: 'http://<server-ip>:5001'
- **Staging**: 'http://<server-ip>:5002'

### Option 2: Manual Run

#### 1. Clone the Repository
```bash
git clone <repository-url>
cd NetMon-Tools-Suite
```

#### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Run the Flask Application
```bash
python app.py
```

#### 4. Access the Application
Open your browser and navigate to `http://<server-ip>:5000`.

## Usage
### Flask Web Interface

1. **Create Project**:
  - Navigate to the "Create Project" section and fill in details like project ID, name, host group, and subscriptions.

2. **Export Graphs**:
  - Choose Zabbix or Grafana graphs and specify the month and year.

3. **Generate Reports**:
  - Generate comprehensive SLA reports for selected projects.

### Command Line
Run scripts directly for specific tasks:

- **Generate Zabbix Report**:
```bash
python zabbix_graph_export.py --month 11 --year 2024 --customer AA001234
```
- **Generate Grafana Report**:
```bash
python generate_report_grafana.py --month 11 --year 2024 --customer AA001234 --llama
```

## File Structure

### Core Application
- **app.py**: Core Flask application for managing project creation, exporting graphs, and generating reports.
- **requirements.txt**: List of Python dependencies for the project.
- **Dockerfile**: Docker configuration for building the application container.
- **docker-compose.yml**: Multi-service configuration for production and staging environments.
- **.gitlab-ci.yml**: CI/CD pipeline configuration for deploying the system to staging or production.

### Scripts
- **zabbix_graph_export.py**: Exports performance and capacity graphs from Zabbix.
- **grafana_graph_export.py**: Exports visual graphs from Grafana dashboards.
- **generate_report.py**: Generates SLA and performance reports using Zabbix data.
- **generate_report_grafana.py**: Generates SLA and performance reports using Grafana data with optional Llama analysis.
- **ticket_fetcher.py**: Fetches and integrates customer tickets into SLA reports.
- **llama_analysis.py**: Performs AI-based analysis on graphs using Llama for trend evaluation.
- **test_availability.py**: Tests system and network availability.
- **test_connection.py**: Simple script to test connectivity to an external API.

### HTML Templates
- **index.html**: Main interface for project and report management.
- **browse.html**: Interface for browsing customer and project files.

### Supporting Tools
- **network_graph_export.py**: Extracts and organizes network-related graphs from Zabbix.
- **grafana_create.py**: Creates Grafana dashboards dynamically based on Zabbix data.

## Deployment Details

### CI/CD Pipeline
The `.gitlab-ci.yml` automates deployments:

- **Staging**:
  - Deploys on branch **staging**.
  - Includes a pre-build cleanup step for temporary directories.

- **Production**:
  - Deploys on branch `main`.
  - Rebuilds and restarts the production container.

### Docker Compose
The docker-compose.yml file manages production and staging environments:

- **Production**:
  - Runs on port 5001.
  - Mounts persistent volumes for report generation.

- **Staging**:
  - Runs on port 5002.

## Contributing
1. Fork the repository.
2. Create a new branch:
```bash
git checkout -b feature/your-feature
```
3. Submit a pull request with detailed changes.

## License
This project is licensed under the MIT License.
