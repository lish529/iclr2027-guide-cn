export interface Paper {
  id: string; number: number | null; title: string; titleZh: string;
  summaryZh: string; primaryArea: string; areaZh: string; subcategory: string;
  tags: string[]; keywords: string[]; status: 'active' | 'inactive';
  classification: 'complete' | 'review' | 'pending'; modified: number | null;
  fingerprint: string; detail: string; rating: number | null;
}
export interface PaperDetail extends Paper { abstract: string; classificationReason?: string }
export interface Manifest {
  schemaVersion: number; sourceUrl: string; snapshotKind: 'sample' | 'complete' | 'incomplete';
  startedAt: string; finishedAt: string; verifiedAt: string | null;
  officialCount: number | null; total: number; classified: number; pending: number;
  review: number; missingAbstract: number; inactive: number; failures: number;
  taxonomyVersion: string; taxonomyStage: string; note: string;
  areas: { name: string; label: string; count: number; subcategories: {name: string; count: number}[] }[];
  tags: {name: string; count: number}[];
  searchShards: string[];
}
export interface Filters { q: string; area: string; sub: string; tags: string[]; state: string; page: number; paper: string }
