/*
  int_utilization_enriched
  ========================
  Provider utilization facts enriched with NPPES provider attributes.
*/

with utilization as (

    select * from {{ ref('stg_cms_provider_utilization') }}

),

providers as (

    select * from {{ ref('int_providers') }}

),

joined as (

    select
        u.utilization_id,
        u.npi,
        coalesce(p.display_name, u.provider_name)                   as provider_name,
        u.specialty                                               as cms_specialty,
        p.primary_taxonomy_code,
        p.entity_type_label,
        p.city                                                    as provider_city,
        p.state                                                   as provider_state,

        u.credentials,
        u.medicare_participating,
        u.hcpcs_code,
        u.hcpcs_description,
        u.is_drug_service,
        u.place_of_service,
        u.service_count,
        u.unique_beneficiary_count,
        u.beneficiary_service_days,
        u.avg_allowed_amount,
        u.avg_submitted_charge,
        u.avg_medicare_payment,
        u.implied_withhold_rate,
        u.year,
        u._loaded_at

    from utilization u
    left join providers p
        on u.npi = p.npi

)

select * from joined
