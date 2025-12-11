import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid';
import Typography from '@mui/material/Typography';
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
  LineChart,
  Line,
} from 'recharts';
import { CongressionalStatus, CongressionalQueryResult } from '../types';

interface CongressionalAnalyticsProps {
  stats: CongressionalStatus['collections']['congressional_data'];
  queryResults?: CongressionalQueryResult[];
}

const PARTY_COLORS: Record<string, string> = {
  Democrat: '#1976d2',
  Republican: '#d32f2f',
  Independent: '#616161',
};

export function CongressionalAnalytics({ stats, queryResults }: CongressionalAnalyticsProps) {
  const memberData = Object.entries(stats.member_counts || {})
    .map(([name, count]) => ({
      name,
      count: count as number,
      party: stats.member_meta?.[name]?.party || 'Unknown',
    }))
    .sort((a, b) => (b.count as number) - (a.count as number))
    .slice(0, 10);

  const partyData = Object.entries(stats.party_counts || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const chamberData = Object.entries(stats.chamber_counts || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const timelineData =
    queryResults && queryResults.length
      ? Object.values(
          queryResults.reduce<Record<string, { date: string; count: number }>>((acc, r) => {
            const day = r.scraped_at.split('T')[0];
            if (!acc[day]) acc[day] = { date: day, count: 0 };
            acc[day].count += 1;
            return acc;
          }, {}),
        ).sort((a, b) => (a.date < b.date ? -1 : 1))
      : [];

  return (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Member Activity (Top 10)" />
          <CardContent sx={{ height: 300 }}>
            {memberData.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No member activity data available.
              </Typography>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={memberData}>
                  <XAxis dataKey="name" hide />
                  <YAxis />
                  <RechartsTooltip />
                  <Bar dataKey="count">
                    {memberData.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={
                          PARTY_COLORS[entry.party] ||
                          '#9e9e9e'
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Party Distribution" />
          <CardContent sx={{ height: 300 }}>
            {partyData.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No party distribution data available.
              </Typography>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={partyData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label
                  >
                    {partyData.map((entry, index) => (
                      <Cell
                        key={index}
                        fill={
                          PARTY_COLORS[entry.name] ||
                          ['#1976d2', '#d32f2f', '#616161', '#9e9e9e'][index % 4]
                        }
                      />
                    ))}
                  </Pie>
                  <Legend />
                  <RechartsTooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Chamber Breakdown" />
          <CardContent sx={{ height: 300 }}>
            {chamberData.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No chamber breakdown data available.
              </Typography>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chamberData} layout="vertical">
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" />
                  <RechartsTooltip />
                  <Bar dataKey="value" fill="#9c27b0" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardHeader title="Timeline (Query Results)" />
          <CardContent sx={{ height: 300 }}>
            {timelineData.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No timeline data available for current query.
              </Typography>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={timelineData}>
                  <XAxis dataKey="date" />
                  <YAxis />
                  <RechartsTooltip />
                  <Line type="monotone" dataKey="count" stroke="#0288d1" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}
