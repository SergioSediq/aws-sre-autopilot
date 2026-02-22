# Contributing to AI SRE

Thanks for your interest in contributing!

## Setup

1. **Clone and install**

   ```bash
   git clone https://github.com/YOUR_USERNAME/Ai-Incident-SRE.git
   cd Ai-Incident-SRE
   pip install -r requirements-dev.txt
   ```

2. **Configure environment**

   ```bash
   cp .env.example .env
   cp infra/terraform.tfvars.example infra/terraform.tfvars
   # Edit with your GEMINI_API_KEY
   ```

## Development

- **Run tests:** `pytest tests/ -v` (or `make test`)
- **Lint:** `ruff check dashboard/ sre-brain/ chaos-scripts/` (or `python -m ruff check ...`)
- **Format:** `ruff format dashboard/ sre-brain/ chaos-scripts/`
- **Dashboard locally:** `cd dashboard && python app.py` (or `make run-dashboard`)
- **Dashboard via Docker:** `make docker-up`
- **Build Lambda zip:** `make build-lambda`

### Pre-commit hooks

Install hooks to run Ruff automatically before each commit:

```bash
pip install pre-commit
pre-commit install
```

## Submitting Changes

1. Create a branch: `git checkout -b feature/your-feature`
2. Make your changes and run tests
3. Commit with a clear message: `git commit -m "Add X"`
4. Push and open a Pull Request

## Code Style

- Python: Follow Ruff defaults (line length 100)
- Terraform: Standard HCL formatting

## Questions?

Open an issue or contact the maintainer.
