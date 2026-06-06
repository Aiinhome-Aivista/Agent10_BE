CSV customer import format

Required columns:

- name
- email

Optional columns (common aliases accepted):

- phone
- dob or date_of_birth
- annual_income
- dependents
- risk_appetite
- kyc_status
- financial_goals (semicolon-separated)
- notes

Example:

name,email,phone,date_of_birth,annual_income,dependents,risk_appetite,financial_goals,notes
Rahul Kumar,rahul@example.com,+919876543210,1990-05-15,1200000,2,MEDIUM,"family protection;retirement","Has family medical history"

Notes:

- The importer normalizes common alternate column names (customer_name/customer_email/dob).
- Each imported user is created with a secure temporary password and must change it on first login.
- If you need a custom mapping, upload a small sample CSV and the system will attempt to normalize using the LLM-backed normalizer.
