You are analyzing a financial transaction to categorize it and provide reasoning.

## Transaction Details:
- Date: {date}
- Description: {name} / {original_description}
- Merchant: {merchant_name}
- Amount: ${amount}
- Bank: {bank_name}
- Location: {location}
- Payment Method: {payment_details}
- Current Plaid Categories: {plaid_categories}

## Available Categories:
{category_options}

Please respond with JSON only. You MUST select one of the available categories exactly as listed above:

{{
  "category": "selected_category",
  "reasoning": "One sentence explaining why this transaction belongs in this category",
  "confidence": "high/medium/low"
}}