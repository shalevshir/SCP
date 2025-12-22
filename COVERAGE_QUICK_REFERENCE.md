# Test Coverage - Quick Reference

## 🚀 Quick Start

```bash
# Test one service
make service-test-coverage SERVICE=execution

# Test all services
make service-test-coverage-all
```

## 📊 Available Services

- `shared` - Shared utilities
- `bot-core` - Signal generation  
- `data-adapter` - Data ingestion
- `execution` - Trade lifecycle
- `feature-engine` - Indicators
- `htf-bias` - HTF analysis

## 📈 Coverage Thresholds

| Status | Coverage | Icon |
|--------|----------|------|
| Excellent | ≥ 80% | 🟢 |
| Good | ≥ 60% | 🟡 |
| Needs Improvement | < 60% | 🔴 |

## 📁 Output Locations

### Individual Service
```
services/<service>/
  ├── coverage_html/index.html   # Interactive report
  ├── coverage.xml               # CI format
  └── coverage.json              # Analysis data
```

### Combined Report
```
coverage_reports/
  ├── coverage_report.md         # Summary table
  └── coverage_summary.json      # Combined data
```

## 🔧 Usage Examples

### Using Scripts Directly
```bash
# Single service
./scripts/test_coverage_service.sh execution

# All services
./scripts/test_coverage_all.sh
```

### Using Make
```bash
# Single service (specify with SERVICE=)
make service-test-coverage SERVICE=execution

# All services
make service-test-coverage-all
```

### View HTML Report
```bash
# After running coverage for execution service
open services/execution/coverage_html/index.html
```

## 🤖 CI/CD Integration

✅ **Automatic on every PR/push:**
- All services tested in parallel
- Individual coverage reports generated  
- Combined coverage report created
- Coverage posted as PR comment
- Artifacts uploaded (retained 30 days)

## 📚 Full Documentation

See [docs/testing-coverage.md](docs/testing-coverage.md) for complete details.

## 💡 Tips

- Run coverage **before** pushing to catch issues early
- Check **HTML reports** for detailed line-by-line coverage
- Aim for **80%+ coverage** on new code
- Focus on **critical paths** and **error handling**

---

**Need Help?** See the [troubleshooting section](docs/testing-coverage.md#troubleshooting) in the full documentation.
