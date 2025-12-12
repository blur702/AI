export interface CongressionalStatus {
  status: string;
  stats: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  paused: boolean;
  collections: {
    congressional_data: {
      exists: boolean;
      object_count: number;
      member_counts?: Record<string, number>;
      party_counts?: Record<string, number>;
      chamber_counts?: Record<string, number>;
      member_meta?: Record<
        string,
        {
          party?: string;
          state?: string;
        }
      >;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
}

export interface CongressionalProgress {
  status: string;
  stats: Record<string, unknown>;
  phase: string;
  message: string;
  current: number;
  total: number;
  paused: boolean;
}

export interface CongressionalChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface CongressionalQueryRequest {
  query: string;
  member_name?: string;
  party?: string;
  state?: string;
  topic?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  messages?: CongressionalChatMessage[];
  conversation_id?: string;
}

export interface CongressionalQueryResult {
  member_name: string;
  state: string;
  district: string;
  party: string;
  chamber: string;
  title: string;
  content_text: string;
  url: string;
  scraped_at: string;
}

export interface CongressionalQueryResponse {
  success: boolean;
  results: CongressionalQueryResult[];
  total_results: number;
  message?: string;
  error?: string;
}

export interface CongressionalScrapeConfig {
  max_members?: number;
  max_pages_per_member?: number;
  dry_run?: boolean;
}

export interface MemberStats {
  name: string;
  count: number;
  party?: string;
  state?: string;
}
