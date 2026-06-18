/*
  stg_cms_part_d_spending
  ========================
  CMS grain: NPI × brand name × generic name × year.
  Surrogate key includes all four; dedupe exact duplicate raw rows.
*/

with source as (

    select * from {{ source('raw_cms', 'cms_part_d_spending') }}

),

renamed as (

    select
        md5(
            coalesce(cast(prscrbr_npi as varchar), '') || '-' ||
            coalesce(cast(brnd_name as varchar), '') || '-' ||
            coalesce(cast(gnrc_name as varchar), '') || '-' ||
            coalesce(cast(year as varchar), '')
        )                                                       as spending_id,

        cast(prscrbr_npi as varchar)                            as npi,
        cast(prscrbr_last_org_name as varchar)                  as provider_name,
        cast(prscrbr_first_name as varchar)                     as provider_first_name,
        cast(prscrbr_city as varchar)                           as provider_city,
        cast(prscrbr_state_abrvtn as varchar)                   as provider_state,
        cast(prscrbr_type as varchar)                           as specialty,

        cast(brnd_name as varchar)                              as drug_name,
        cast(gnrc_name as varchar)                              as generic_name,

        case
            when tot_benes in ('', '*', 'NA') or tot_benes is null then null
            else cast(tot_benes as integer)
        end                                                     as bene_count,

        cast(tot_clms as integer)                               as total_claim_count,
        cast(tot_day_suply as integer)                          as total_day_supply,
        cast(tot_drug_cst as numeric(18, 2))                    as total_drug_cost,

        cast(year as integer)                                   as year,
        cast(_loaded_at as timestamp)                             as source_loaded_at,
        current_timestamp                                       as _loaded_at

    from source

    where prscrbr_npi is not null
      and prscrbr_npi != ''

),

deduped as (

    select
        *,
        row_number() over (
            partition by spending_id
            order by source_loaded_at desc nulls last
        ) as rn

    from renamed

)

select
    spending_id,
    npi,
    provider_name,
    provider_first_name,
    provider_city,
    provider_state,
    specialty,
    drug_name,
    generic_name,
    bene_count,
    total_claim_count,
    total_day_supply,
    total_drug_cost,
    year,
    _loaded_at

from deduped

where rn = 1
