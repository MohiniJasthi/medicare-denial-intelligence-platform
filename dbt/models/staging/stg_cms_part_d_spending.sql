/*
  stg_cms_part_d_spending
  ========================
  Staged Medicare Part D Drug Spending by Provider and Drug.
  One row per provider (NPI) × drug × year.

  Transformations:
    - Renames columns to snake_case analytical names
    - Casts numeric strings to proper types
    - Filters out rows with null NPI (ungrouped summary rows in CMS data)
    - Generates a surrogate key from npi + drug_name + year
*/

with source as (

    select * from {{ source('raw_cms', 'cms_part_d_spending') }}

),

renamed as (

    select
        -- Surrogate key (md5 instead of dbt_utils to avoid package dependency)
        md5(
            coalesce(cast(npi as varchar), '') || '-' ||
            coalesce(cast(drug_name as varchar), '') || '-' ||
            coalesce(cast(year as varchar), '')
        )                                                       as spending_id,

        -- Provider identifiers
        cast(npi as varchar)                                    as npi,
        cast(nppes_provider_last_org_name as varchar)           as provider_name,
        cast(nppes_provider_first_name as varchar)              as provider_first_name,
        cast(nppes_provider_city as varchar)                    as provider_city,
        cast(nppes_provider_state as varchar)                   as provider_state,
        cast(specialty_description as varchar)                  as specialty,

        -- Drug details
        cast(drug_name as varchar)                              as drug_name,
        cast(generic_name as varchar)                           as generic_name,

        -- Metrics — suppress suppressed/blank values (CMS suppresses <11)
        case
            when bene_count = '' or bene_count is null then null
            else cast(bene_count as integer)
        end                                                     as bene_count,

        cast(total_claim_count as integer)                      as total_claim_count,
        cast(total_day_supply as integer)                       as total_day_supply,
        cast(total_drug_cost as numeric(18, 2))                 as total_drug_cost,

        -- Year partition (present in multi-year CMS exports)
        cast(year as integer)                                   as year,

        -- Audit
        current_timestamp                                       as _loaded_at

    from source

    where npi is not null
      and npi != ''

)

select * from renamed
