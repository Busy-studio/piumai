-- PIUM AI - 대학정보공시 저장 테이블
-- Supabase SQL Editor에서 1회 실행하세요.
-- year = 조사연도(exmnYr), application_year = 적용연도(aplcnYr)

create table if not exists public.university_patent_stats (
    school_name text not null,
    branch_yn text not null default '',
    year integer not null,
    application_year integer,
    domestic_patent_applications bigint,
    domestic_patent_registrations bigint,
    overseas_patent_applications bigint,
    overseas_patent_registrations bigint,
    created_at timestamptz not null default now(),
    primary key (school_name, branch_yn, year)
);

create table if not exists public.university_transfer_stats (
    school_name text not null,
    branch_yn text not null default '',
    year integer not null,
    application_year integer,
    transfer_contracts bigint,
    transfer_income numeric(20,0),
    created_at timestamptz not null default now(),
    primary key (school_name, branch_yn, year)
);

-- 기존 스키마를 이미 실행한 경우에도 안전하게 적용
alter table public.university_patent_stats
    add column if not exists application_year integer;
alter table public.university_transfer_stats
    add column if not exists application_year integer;

create table if not exists public.university_disclosure_sync (
    source text not null check (source in ('patent', 'transfer')),
    year integer not null,
    row_count integer not null default 0,
    synced_at timestamptz not null default now(),
    primary key (source, year)
);

comment on column public.university_patent_stats.year is '조사연도 exmnYr';
comment on column public.university_patent_stats.application_year is '적용연도 aplcnYr';
comment on column public.university_transfer_stats.year is '조사연도 exmnYr';
comment on column public.university_transfer_stats.application_year is '적용연도 aplcnYr';

alter table public.university_patent_stats enable row level security;
alter table public.university_transfer_stats enable row level security;
alter table public.university_disclosure_sync enable row level security;

revoke all on table public.university_patent_stats from anon, authenticated;
revoke all on table public.university_transfer_stats from anon, authenticated;
revoke all on table public.university_disclosure_sync from anon, authenticated;

grant select, insert, update, delete on table public.university_patent_stats to service_role;
grant select, insert, update, delete on table public.university_transfer_stats to service_role;
grant select, insert, update, delete on table public.university_disclosure_sync to service_role;
