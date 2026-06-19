/*
  int_providers
  =============
  Canonical provider dimension from NPPES with a human-readable display name.
*/

with providers as (

    select * from {{ ref('stg_nppes_providers') }}

),

final as (

    select
        npi,
        entity_type,
        org_name,
        last_name,
        first_name,
        credentials,
        city,
        state,
        zip,
        primary_taxonomy_code,
        is_sole_proprietor,

        coalesce(
            case
                when entity_type = '2' then nullif(trim(org_name), '')
                else nullif(trim(coalesce(first_name, '') || ' ' || coalesce(last_name, '')), '')
            end,
            npi
        )                                                           as display_name,

        case
            when entity_type = '2' then 'organization'
            when entity_type = '1' then 'individual'
            else 'unknown'
        end                                                         as entity_type_label,

        current_timestamp                                           as _updated_at

    from providers

)

select * from final
