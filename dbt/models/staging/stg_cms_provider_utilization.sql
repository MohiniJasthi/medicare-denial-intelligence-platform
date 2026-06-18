/*
  stg_cms_provider_utilization
  =============================
  CMS grain: NPI × HCPCS code × place of service × year.
  Same provider + procedure can appear for office vs facility settings.
*/

with source as (

    select * from {{ source('raw_cms', 'cms_provider_utilization') }}

),

renamed as (

    select
        md5(
            coalesce(cast(rndrng_npi as varchar), '') || '-' ||
            coalesce(cast(hcpcs_cd as varchar), '') || '-' ||
            coalesce(cast(place_of_srvc as varchar), '') || '-' ||
            coalesce(cast(year as varchar), '')
        )                                                           as utilization_id,

        cast(rndrng_npi as varchar)                                 as npi,
        cast(rndrng_prvdr_last_org_name as varchar)                 as provider_name,
        cast(rndrng_prvdr_crdntls as varchar)                       as credentials,
        cast(null as varchar)                                       as gender,
        cast(rndrng_prvdr_ent_cd as varchar)                        as entity_type,
        cast(rndrng_prvdr_city as varchar)                          as city,
        cast(rndrng_prvdr_state_abrvtn as varchar)                  as state,
        cast(rndrng_prvdr_type as varchar)                          as specialty,

        cast(rndrng_prvdr_mdcr_prtcptg_ind as varchar)              as medicare_participating,

        cast(hcpcs_cd as varchar)                                   as hcpcs_code,
        cast(hcpcs_desc as varchar)                                 as hcpcs_description,
        cast(hcpcs_drug_ind as varchar)                             as is_drug_service,
        cast(place_of_srvc as varchar)                              as place_of_service,

        cast(tot_srvcs as numeric)                                  as service_count,
        cast(tot_benes as integer)                                  as unique_beneficiary_count,
        cast(tot_bene_day_srvcs as integer)                         as beneficiary_service_days,

        cast(avg_mdcr_alowd_amt as numeric(18, 2))                  as avg_allowed_amount,
        cast(avg_sbmtd_chrg as numeric(18, 2))                      as avg_submitted_charge,
        cast(avg_mdcr_pymt_amt as numeric(18, 2))                   as avg_medicare_payment,

        round(
            1.0 - (
                cast(avg_mdcr_pymt_amt as numeric(18, 2)) /
                nullif(cast(avg_mdcr_alowd_amt as numeric(18, 2)), 0)
            ), 4
        )                                                           as implied_withhold_rate,

        cast(year as integer)                                       as year,
        cast(_loaded_at as timestamp)                                 as source_loaded_at,
        current_timestamp                                           as _loaded_at

    from source

    where rndrng_npi is not null
      and rndrng_npi != ''
      and hcpcs_cd is not null
      and hcpcs_cd != ''

),

deduped as (

    select
        *,
        row_number() over (
            partition by utilization_id
            order by source_loaded_at desc nulls last
        ) as rn

    from renamed

)

select
    utilization_id,
    npi,
    provider_name,
    credentials,
    gender,
    entity_type,
    city,
    state,
    specialty,
    medicare_participating,
    hcpcs_code,
    hcpcs_description,
    is_drug_service,
    place_of_service,
    service_count,
    unique_beneficiary_count,
    beneficiary_service_days,
    avg_allowed_amount,
    avg_submitted_charge,
    avg_medicare_payment,
    implied_withhold_rate,
    year,
    _loaded_at

from deduped

where rn = 1
