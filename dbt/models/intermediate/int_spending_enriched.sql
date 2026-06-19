/*
  int_spending_enriched
  =====================
  Part D spending facts enriched with NPPES provider attributes.
*/

with spending as (

    select * from {{ ref('stg_cms_part_d_spending') }}

),

providers as (

    select * from {{ ref('int_providers') }}

),

joined as (

    select
        s.spending_id,
        s.npi,
        coalesce(p.display_name, s.provider_name)                 as provider_name,
        coalesce(p.city, s.provider_city)                         as provider_city,
        coalesce(p.state, s.provider_state)                         as provider_state,
        coalesce(p.primary_taxonomy_code, s.specialty)              as provider_taxonomy_or_specialty,
        p.entity_type_label,

        s.drug_name,
        s.generic_name,
        s.bene_count,
        s.total_claim_count,
        s.total_day_supply,
        s.total_drug_cost,
        s.year,
        s._loaded_at

    from spending s
    left join providers p
        on s.npi = p.npi

)

select * from joined
