-- PIUM AI - 대학정보공시 저장 테이블
-- Supabase SQL Editor에서 1회 실행하세요.

create table if not exists public.university_patent_stats (
    school_name text not null,
    branch_yn text not null default '',
    year integer not null,
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
    transfer_contracts bigint,
    transfer_income numeric(20,0),
    created_at timestamptz not null default now(),
    primary key (school_name, branch_yn, year)
);

create table if not exists public.university_disclosure_sync (
    source text not null check (source in ('patent', 'transfer')),
    year integer not null,
    row_count integer not null default 0,
    synced_at timestamptz not null default now(),
    primary key (source, year)
);

alter table public.university_patent_stats enable row level security;
alter table public.university_transfer_stats enable row level security;
alter table public.university_disclosure_sync enable row level security;

revoke all on table public.university_patent_stats from anon, authenticated;
revoke all on table public.university_transfer_stats from anon, authenticated;
revoke all on table public.university_disclosure_sync from anon, authenticated;

grant select, insert, update, delete on table public.university_patent_stats to service_role;
grant select, insert, update, delete on table public.university_transfer_stats to service_role;
grant select, insert, update, delete on table public.university_disclosure_sync to service_role;
