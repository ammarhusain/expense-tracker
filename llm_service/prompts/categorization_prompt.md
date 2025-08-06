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

**paychecks**: Regular salary payments from employers
**interest_income**: Interest earned from bank accounts, CDs, bonds
**business_income**: Revenue from business activities or freelance work
**investment_income**: Dividends, capital gains, investment returns

**charity**: Donations to charitable organizations
**gifts**: Money given to family, friends, or others

**auto_payment**: Car loan or lease payments
**public_transit**: Bus, train, subway fares
**gas**: Gasoline for vehicles
**auto_maintenance**: Car repairs, oil changes, maintenance
**parking_or_tolls**: Parking fees, toll road charges
**taxi_or_ride_shares**: Uber, Lyft, taxi services

**mortgage**: Monthly mortgage payments
**rent**: Monthly rental payments
**furniture**: Furniture purchases for home
**home_maintenance**: Home repairs, maintenance services
**remodel**: Home renovation, remodeling expenses

**garbage**: Waste management services
**water**: Water utility bills
**gas_and_electric**: Gas and electric utility bills
**internet**: Internet service provider bills
**phone**: Mobile or landline phone bills
**software_subscriptions**: Software, streaming, app subscriptions

**groceries**: Food shopping at grocery stores
**restaurants_or_bars**: Dining out, bars, takeout
**coffee_shops**: Coffee shops, cafes

**travel_general**: General travel expenses
**airfare**: Flight tickets
**accommodation**: Hotels, lodging

**shopping**: General retail purchases
**clothing**: Apparel, shoes, accessories
**housewares**: Household items, home goods
**electronics**: Electronics, gadgets, tech purchases

**personal_grooming**: Haircuts, beauty services, cosmetics
**hobbies**: Hobby supplies, craft materials
**education**: Educational expenses, courses, books
**entertainment_or_recreation**: Movies, concerts, recreational activities

**medical**: Doctor visits, medical expenses
**dental**: Dental care expenses
**fitness**: Gym memberships, fitness services

**loan_repayment**: Loan payments (non-auto, non-mortgage)
**financial_legal_services**: Banking fees, legal services
**atm_cash_withdrawal**: ATM cash withdrawals
**insurance**: Insurance premiums for cars and home
**taxes**: Tax payments to IRS or property taxes
**penalties**: Late fees, penalties
**hand_loans**: Personal loans to/from individuals
**invest**: Investment purchases and usually transfers into brokerage accounts

**uncategorized**: Catch all category for items that don't fit other categories or you cannot figure out with high confidence where to put it 
**miscellaneous**: Various small expenses
**reimburse**: Reimbursements received usally as deposits from Venmo or Zelle

**transfer**: Money transfers between own accounts
**credit_card_payment**: Credit card bill payments
**to_india**: Money transfers to India usually money sent to Revolut

Please respond with JSON only. You MUST select one of the available categories exactly as listed above:

{
  "reasoning": "Short and succinct phrase explaining why this transaction belongs in this category",
  "category": "selected_category"
}