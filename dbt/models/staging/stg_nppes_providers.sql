/*
  stg_nppes_providers
  ====================
  Staged NPI Provider Registry from NPPES bulk download (V2).
  Deduplicated to one row per NPI.

  NPPES V2 headers include parentheses, e.g.:
    "Provider Organization Name (Legal Business Name)"
  which the loader normalizes to:
    provider_organization_name_(legal_business_name)
*/

with source as (

    select * from {{ source('raw_cms', 'nppes_providers') }}

),

deduped as (

    select
        *,
        row_number() over (
            partition by npi
            order by npi
        ) as rn

    from source

    where npi is not null
      and npi != ''

),

renamed as (

    select
        cast(npi as varchar)                                                            as npi,
        cast(entity_type_code as varchar)                                               as entity_type,

        coalesce(
            cast("provider_organization_name_(legal_business_name)" as varchar),
            cast(provider_other_organization_name as varchar)
        )                                                                               as org_name,

        cast("provider_last_name_(legal_name)" as varchar)                                as last_name,
        cast(provider_first_name as varchar)                                            as first_name,
        cast(provider_credential_text as varchar)                                       as credentials,

        cast(provider_business_practice_location_address_city_name as varchar)          as city,
        cast(provider_business_practice_location_address_state_name as varchar)         as state,
        cast(provider_business_practice_location_address_postal_code as varchar)        as zip,

        cast(healthcare_provider_taxonomy_code_1 as varchar)                            as primary_taxonomy_code,
        cast(is_sole_proprietor as varchar)                                             as is_sole_proprietor,

        current_timestamp                                                               as _loaded_at

    from deduped

    where rn = 1

)

select * from renamed
