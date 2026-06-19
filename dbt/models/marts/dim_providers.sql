/*
  dim_providers
  =============
  Provider dimension mart — one row per NPI for joins and dashboards.
*/

select
    npi,
    entity_type,
    entity_type_label,
    display_name,
    org_name,
    last_name,
    first_name,
    credentials,
    city,
    state,
    zip,
    primary_taxonomy_code,
    is_sole_proprietor,
    _updated_at

from {{ ref('int_providers') }}
