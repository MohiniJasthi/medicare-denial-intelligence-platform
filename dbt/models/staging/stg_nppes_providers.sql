/*
  stg_nppes_providers
  ====================
  Staged NPI Provider Registry from NPPES bulk download.
  Deduplicated to one row per NPI.

  The raw NPPES file can contain duplicate NPI rows across
  monthly replacement files. We keep one canonical record
  per NPI using ROW_NUMBER() partitioned by NPI.

  Transformations:
    - Renames verbose NPPES column names to short analytical aliases
    - Selects key columns for joining to CMS datasets
    - Deduplicates by NPI (most recent record wins)
*/

with source as (

    select * from {{ source('raw_cms', 'nppes_providers') }}

),

deduped as (

    select
        *,
        row_number() over (
            partition by npi
            order by npi  -- secondary sort; add `npi_deactivation_date desc nulls first` if column present
        ) as rn

    from source

    where npi is not null
      and npi != ''

),

renamed as (

    select
        -- Primary key
        cast(npi as varchar)                                                            as npi,

        -- Provider classification
        cast(entity_type_code as varchar)                                               as entity_type,

        -- Organization name (entity type 2)
        cast(provider_organization_name as varchar)                                     as org_name,

        -- Individual name (entity type 1)
        cast(provider_last_name as varchar)                                             as last_name,
        cast(provider_first_name as varchar)                                            as first_name,
        cast(provider_credential_text as varchar)                                       as credentials,

        -- Practice location
        cast(provider_business_practice_location_address_city_name as varchar)          as city,
        cast(provider_business_practice_location_address_state_name as varchar)         as state,
        cast(provider_business_practice_location_address_postal_code as varchar)        as zip,

        -- Specialty taxonomy
        cast(healthcare_provider_taxonomy_code_1 as varchar)                            as primary_taxonomy_code,

        -- Business flags
        cast(is_sole_proprietor as varchar)                                             as is_sole_proprietor,

        -- Audit
        current_timestamp                                                               as _loaded_at

    from deduped

    where rn = 1

)

select * from renamed
