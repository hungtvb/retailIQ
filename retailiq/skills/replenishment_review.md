# Replenishment Review Skill
- Combine top seller's completed-order unit sales (current synthetic month) with available units for that SKU.
- Calculate `coverage_ratio = available_units / units_sold` only if units_sold > 0.
- If available_units < units_sold, flag **review replenishment priority**; otherwise say **no immediate priority under this heuristic**.
- This is an illustrative heuristic, NOT a demand forecast, safety-stock policy, purchase order, or inventory mutation.
- Explain assumptions, source dates, and uncertainty in the final answer.
