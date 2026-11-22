Research database for the FirstStep prototype.

- 1,499,965 source data rows across subject tables, excluding the geography lookup.
- 330,954 distinct geographic areas; geographies repeat across subject tables.
- 2020–2024 ACS five-year population, income, employment, parental employment, and vehicle-access estimates and margins of error.
- 48,308 historical county-year records from the Department of Labor's 2008–2022 National Database of Childcare Prices.
- 39,184 California childcare center/family-home licensing source records across statuses, dated May 25, 2025.

The ZIP includes the 304 MB SQLite database, county extract, Census field dictionary, source manifest, example queries, coverage counts, and documentation. Database integrity, geographic joins, dictionary labels, example queries, and ZIP integrity were checked.

These are research data, not live vacancies, individual applicant records, current eligibility decisions, provider commitments, or measured outcomes. Source terms and attribution are documented in START_HERE.txt and the application README. The application code license does not replace dataset terms.

Install from the cloned repository:

```sh
gh release download research-v1 --repo am101596-sketch/jestergooning --pattern FirstStep_Database.zip --dir data
python scripts/install_database.py data/FirstStep_Database.zip
```
