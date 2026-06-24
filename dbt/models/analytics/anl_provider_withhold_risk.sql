/*
  anl_provider_withhold_risk
  ==========================
  Provider-year withhold risk flags vs specialty median (for outlier analytics).
  Grain: NPI × specialty × state × year. Filtered to providers with >= 5 service lines.
*/

with provider_year as (
    select
        u.npi,
        max(u.provider_name) as provider_name,
        u.cms_specialty,
        u.provider_state,
        u.year,
        round(avg(u.implied_withhold_rate)::numeric, 4) as avg_withhold_rate,
        count(*) as service_line_count,
        sum(u.service_count) as total_services,
        round(avg(u.avg_medicare_payment)::numeric, 2) as avg_medicare_payment
    from {{ ref('int_utilization_enriched') }} u
    where u.implied_withhold_rate is not null
      and u.cms_specialty is not null
    group by u.npi, u.cms_specialty, u.provider_state, u.year
    having count(*) >= 5
),

specialty_medians as (
    -- National specialty median: aggregate state-level mart rows to specialty × year
    select
        specialty as cms_specialty,
        year,
        round(
            sum(median_withhold_rate * provider_count) / nullif(sum(provider_count), 0),
            4
        ) as specialty_median_withhold
    from {{ ref('fct_utilization_by_specialty') }}
    where specialty <> 'Unknown'
    group by specialty, year
)

select
  md5(
    p.npi || '-' || coalesce(p.cms_specialty, '') || '-' ||
    coalesce(p.provider_state, '') || '-' || coalesce(cast(p.year as varchar), '')
  ) as provider_risk_id,
    p.npi,
    p.provider_name,
    p.cms_specialty,
    p.provider_state,
    p.year,
    p.avg_withhold_rate,
    s.specialty_median_withhold,
    round((p.avg_withhold_rate - s.specialty_median_withhold)::numeric, 4) as withhold_vs_median,
    case
        when p.avg_withhold_rate > s.specialty_median_withhold then 'High'
        when p.avg_withhold_rate < s.specialty_median_withhold then 'Low'
        else 'At Median'
    end as withhold_risk_band,
    p.service_line_count,
    p.total_services,
    p.avg_medicare_payment,
    current_timestamp as _updated_at
from provider_year p
inner join specialty_medians s
    on p.cms_specialty = s.cms_specialty
   and p.year = s.year
