/*
  fct_provider_spending
  =====================
  Part D spending fact table at provider × drug × year grain.
*/

select
    spending_id,
    npi,
    provider_name,
    provider_city,
    provider_state,
    provider_taxonomy_or_specialty,
    entity_type_label,
    drug_name,
    generic_name,
    bene_count,
    total_claim_count,
    total_day_supply,
    total_drug_cost,
    year,
    _loaded_at

from {{ ref('int_spending_enriched') }}
