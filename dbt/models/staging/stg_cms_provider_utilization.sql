/*
  stg_cms_provider_utilization
  =============================
  Staged Medicare Provider Utilization and Payment Data.
  One row per provider (NPI) × HCPCS procedure code.

  Transformations:
    - Renames columns to readable analytical names
    - Casts financial amounts to numeric(18,2)
    - Filters rows missing NPI or HCPCS code (data quality guard)
    - Generates a surrogate key from npi + hcpcs_code
*/

with source as (

    select * from {{ source('raw_cms', 'cms_provider_utilization') }}

),

renamed as (

    select
        -- Surrogate key
        md5(
            coalesce(cast(npi as varchar), '') || '-' ||
            coalesce(cast(hcpcs_code as varchar), '')
        )                                                           as utilization_id,

        -- Provider identifiers
        cast(npi as varchar)                                        as npi,
        cast(nppes_provider_last_org_name as varchar)               as provider_name,
        cast(nppes_credentials as varchar)                          as credentials,
        cast(nppes_provider_gender as varchar)                      as gender,
        cast(nppes_entity_code as varchar)                          as entity_type,
        cast(nppes_provider_city as varchar)                        as city,
        cast(nppes_provider_state as varchar)                       as state,
        cast(provider_type as varchar)                              as specialty,

        -- Participation flags
        cast(medicare_participation_indicator as varchar)           as medicare_participating,

        -- Procedure / service
        cast(hcpcs_code as varchar)                                 as hcpcs_code,
        cast(hcpcs_description as varchar)                          as hcpcs_description,
        cast(hcpcs_drug_indicator as varchar)                       as is_drug_service,

        -- Utilization metrics
        cast(line_srvc_cnt as numeric)                              as service_count,
        cast(bene_unique_cnt as integer)                            as unique_beneficiary_count,
        cast(bene_day_srvc_cnt as integer)                          as beneficiary_service_days,

        -- Payment metrics
        cast(average_medicare_allowed_amt as numeric(18, 2))        as avg_allowed_amount,
        cast(average_submitted_chrg_amt as numeric(18, 2))          as avg_submitted_charge,
        cast(average_medicare_payment_amt as numeric(18, 2))        as avg_medicare_payment,

        -- Derived: implied denial / withholding rate
        round(
            1.0 - (
                cast(average_medicare_payment_amt as numeric(18, 2)) /
                nullif(cast(average_medicare_allowed_amt as numeric(18, 2)), 0)
            ), 4
        )                                                           as implied_withhold_rate,

        -- Audit
        current_timestamp                                           as _loaded_at

    from source

    where npi is not null
      and npi != ''
      and hcpcs_code is not null
      and hcpcs_code != ''

)

select * from renamed
