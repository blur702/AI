import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActions from "@mui/material/CardActions";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { CongressionalQueryResult } from "../types";

interface CongressionalResultCardProps {
  result: CongressionalQueryResult;
  onMemberClick?: (memberName: string) => void;
}

function getPartyColor(party: string): "default" | "primary" | "secondary" {
  if (party.toLowerCase().startsWith("dem")) return "primary";
  if (party.toLowerCase().startsWith("rep")) return "secondary";
  return "default";
}

export function CongressionalResultCard({
  result,
  onMemberClick,
}: CongressionalResultCardProps) {
  const handleCopyUrl = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(result.url).catch(() => {});
    }
  };

  const contentPreview =
    result.content_text.length > 200
      ? `${result.content_text.slice(0, 200)}…`
      : result.content_text;

  return (
    <Card
      variant="outlined"
      sx={{
        borderLeft: 4,
        borderLeftColor:
          getPartyColor(result.party) === "primary"
            ? "primary.main"
            : getPartyColor(result.party) === "secondary"
              ? "secondary.main"
              : "divider",
        "&:hover": { boxShadow: 3 },
      }}
    >
      <CardContent>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mb: 1,
            flexWrap: "wrap",
            gap: 1,
          }}
        >
          <Chip
            label={result.member_name}
            size="small"
            onClick={
              onMemberClick
                ? () => onMemberClick(result.member_name)
                : undefined
            }
            sx={{ cursor: onMemberClick ? "pointer" : "default" }}
          />
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Chip
              label={result.party || "Unknown"}
              size="small"
              color={getPartyColor(result.party)}
            />
            <Chip
              label={`${result.state}${result.district ? `-${result.district}` : ""}`}
              size="small"
              variant="outlined"
            />
            <Chip label={result.chamber} size="small" variant="outlined" />
          </Box>
        </Box>

        <Typography variant="subtitle1" gutterBottom>
          {result.title || "Untitled"}
        </Typography>

        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 1.5, whiteSpace: "pre-line" }}
        >
          {contentPreview}
        </Typography>

        <Typography variant="caption" color="text.secondary">
          Scraped at: {result.scraped_at}
        </Typography>
      </CardContent>
      <CardActions sx={{ justifyContent: "space-between" }}>
        <Button
          size="small"
          href={result.url}
          target="_blank"
          rel="noopener noreferrer"
          startIcon={<OpenInNewIcon />}
        >
          Open
        </Button>
        <Tooltip title="Copy URL">
          <Button
            size="small"
            onClick={handleCopyUrl}
            startIcon={<ContentCopyIcon />}
          >
            Copy URL
          </Button>
        </Tooltip>
      </CardActions>
    </Card>
  );
}
