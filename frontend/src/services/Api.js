import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001";

const API = axios.create({ baseURL });

const withRefresh = (path, refresh) => `${path}${refresh ? "?refresh=true" : ""}`;

export const fetchOverview    = (refresh = false) => API.get(withRefresh("/overview", refresh));
export const fetchJoiners     = (refresh = false) => API.get(withRefresh("/joiners", refresh));
export const fetchMovers      = (refresh = false) => API.get(withRefresh("/movers", refresh));
export const fetchLeavers     = (refresh = false) => API.get(withRefresh("/leavers", refresh));
export const fetchPrivileged  = (refresh = false) => API.get(withRefresh("/privileged", refresh));
export const fetchGuests      = (refresh = false) => API.get(withRefresh("/guests", refresh));
export const fetchAgent       = (query) => API.post("/agent", { query });

export default API;
