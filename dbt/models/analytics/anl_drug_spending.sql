/*
  anl_drug_spending
  =================
  Drug-level Part D spending by year for Pareto and ranking analysis.
*/

select
    coalesce(drug_name, generic_name, 'Unknown') as drug_name,
    generic_name,
    year,
    count(distinct npi) as prescriber_count,
    sum(total_claim_count) as total_claims,
    sum(total_day_supply) as total_day_supply,
    round(sum(total_drug_cost)::numeric, 2) as total_medicare_cost,
    round(avg(total_drug_cost)::numeric, 2) as avg_cost_per_row
from {{ ref('fct_provider_spending') }}
where drug_name is not null or generic_name is not null
group by 1, 2, 3
