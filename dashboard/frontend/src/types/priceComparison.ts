/**
 * Price Comparison TypeScript Types
 *
 * Interfaces matching the backend API response structure for grocery
 * price comparison across multiple services.
 */

// Product attributes extracted by LLM analysis
export interface ProductAttributes {
  brand: string | null;
  size: string | null;
  size_oz: number | null;
  unit_price: number | null;
  is_organic: boolean;
  product_type: string | null;
  confidence: number;
}

// Individual product from a grocery service
export interface Product {
id: string;
service: string;
name: string;
price: string;
size: string | null;

// Group of comparable products identified by LLM
export interface ProductGroup {
  representative_name: string;
  reasoning: string;
  products: Product[];
}

// Full comparison result from search
export interface ComparisonResult {
  comparison_id: string | null;
  query: string;
  location: string;
  status: "completed" | "error" | "in_progress";
  services_scraped: string[];
  groups: ProductGroup[];
  llm_analysis: string | null;
  model_used: string | null;
  from_cache: boolean;
  errors: string[];
}

// WebSocket progress update during scraping
export interface SearchProgress {
  service: string;
  status: "starting" | "scraping" | "complete" | "error";
  current: number;
  total: number;
  message: string;
}

// Saved product selection
export interface SavedSelection {
  selection_id: string;
  product: Product;
  quantity: number;
  notes: string | null;
  created_at: string;
}

// Shopping list item for bulk upload
export interface ShoppingListItem {
  name: string;
  quantity: number;
  notes?: string;
}

// Bulk upload response
export interface BulkUploadResult {
  list_id: string | null;
  job_id: string | null;
  status: "completed" | "error" | "processing";
  name: string | null;
  items: ShoppingListItemResult[];
  total_stats: ShoppingListStats | null;
  message?: string;
}

// Individual item result from bulk upload
export interface ShoppingListItemResult {
  name: string;
  quantity: number;
  comparison_id: string | null;
  status: "completed" | "error";
  best_price: number | null;
  best_service: string | null;
}

// Aggregate statistics for shopping list
export interface ShoppingListStats {
  total_items: number;
  items_found: number;
  lowest_total_by_service: Record<string, number>;
  potential_savings: number;
  recommended_service: string | null;
}

// API request types
export interface ProductSearchRequest {
  query: string;
  location?: string;
  services?: string[];
}

export interface BulkUploadRequest {
  items: ShoppingListItem[];
  session_token?: string;
  name?: string;
}

// Available grocery services
export type GroceryService =
  | "amazon_fresh"
  | "instacart"
  | "doordash"
  | "safeway";

export const GROCERY_SERVICES: {
  id: GroceryService;
  name: string;
  color: string;
}[] = [
  { id: "amazon_fresh", name: "Amazon Fresh", color: "#FF9900" },
  { id: "instacart", name: "Instacart", color: "#43B02A" },
  { id: "doordash", name: "DoorDash", color: "#FF3008" },
  { id: "safeway", name: "Safeway", color: "#E31837" },
];

// Helper to get service color
export function getServiceColor(service: string): string {
  const found = GROCERY_SERVICES.find(
    (s) => s.id === service || s.name.toLowerCase() === service.toLowerCase()
  );
  return found?.color ?? "#9E9E9E";
}

// Helper to get service display name
export function getServiceName(service: string): string {
  const found = GROCERY_SERVICES.find(
    (s) => s.id === service || s.name.toLowerCase() === service.toLowerCase()
  );
  return found?.name ?? service;
}
