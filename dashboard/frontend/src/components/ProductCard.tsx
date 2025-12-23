import { memo } from "react";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActions from "@mui/material/CardActions";
import CardMedia from "@mui/material/CardMedia";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import AddShoppingCartIcon from "@mui/icons-material/AddShoppingCart";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import SpaIcon from "@mui/icons-material/Spa";
import { Product, getServiceColor, getServiceName } from "../types";

interface ProductCardProps {
  product: Product;
  onSave?: (productId: string) => void;
  highlighted?: boolean;
}

function getSimilarityColor(score: number): "success" | "warning" | "error" {
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  return "error";
}

function formatPrice(price: number): string {
  return `$${price.toFixed(2)}`;
}

export const ProductCard = memo(function ProductCard({
  product,
  onSave,
  highlighted = false,
}: ProductCardProps) {
  const serviceColor = getServiceColor(product.service);
  const serviceName = getServiceName(product.service);
  const similarityPercent = Math.round(product.similarity_score * 100);

  const handleOpenProduct = () => {
    if (product.url) {
      window.open(product.url, "_blank", "noopener,noreferrer");
    }
  };

  const handleSave = () => {
    if (onSave) {
      onSave(product.id);
    }
  };

  return (
    <Card
      elevation={highlighted ? 4 : 2}
      sx={{
        position: "relative",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        borderLeft: `4px solid ${serviceColor}`,
        transition: "all 0.3s ease",
        ...(highlighted && {
          border: `2px solid`,
          borderColor: "success.main",
          borderLeftWidth: 4,
          borderLeftColor: serviceColor,
        }),
        "&:hover": {
          transform: "translateY(-5px)",
          boxShadow: 6,
        },
      }}
    >
      {/* Best Price Badge */}
      {highlighted && (
        <Chip
          icon={<LocalOfferIcon />}
          label="Best Price"
          color="success"
          size="small"
          sx={{
            position: "absolute",
            top: 8,
            right: 8,
            zIndex: 1,
            fontWeight: 600,
          }}
        />
      )}

      {/* Product Image */}
      {product.image_url ? (
        <CardMedia
          component="img"
          height="140"
          image={product.image_url}
          alt={product.name}
          sx={{
            objectFit: "contain",
            bgcolor: "background.default",
            p: 1,
          }}
        />
      ) : (
        <Box
          sx={{
            height: 140,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            bgcolor: "action.hover",
          }}
        >
          <Typography variant="caption" color="text.secondary">
            No image
          </Typography>
        </Box>
      )}

      <CardContent sx={{ flexGrow: 1, pb: 1 }}>
        {/* Service Name */}
        <Chip
          label={serviceName}
          size="small"
          sx={{
            mb: 1,
            bgcolor: serviceColor,
            color: "white",
            fontWeight: 600,
            fontSize: "0.7rem",
          }}
        />

        {/* Product Name */}
        <Typography
          variant="subtitle1"
          component="h3"
          sx={{
            fontWeight: 600,
            lineHeight: 1.3,
            mb: 1,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {product.name}
        </Typography>

        {/* Price */}
        <Typography
          variant="h5"
          color="primary"
          sx={{ fontWeight: 700, mb: 1 }}
        >
          {formatPrice(product.price)}
        </Typography>

        {/* Product Details */}
        <Stack
          direction="row"
          spacing={0.5}
          flexWrap="wrap"
          useFlexGap
          sx={{ mb: 1 }}
        >
          {product.size && (
            <Chip
              label={product.size}
              size="small"
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 22 }}
            />
          )}
          {product.brand && (
            <Chip
              label={product.brand}
              size="small"
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 22 }}
            />
          )}
          {product.attributes?.is_organic && (
            <Tooltip title="Organic Product">
              <Chip
                icon={<SpaIcon sx={{ fontSize: "0.9rem" }} />}
                label="Organic"
                size="small"
                color="success"
                variant="outlined"
                sx={{ fontSize: "0.7rem", height: 22 }}
              />
            </Tooltip>
          )}
        </Stack>

        {/* Unit Price */}
        {product.attributes?.unit_price && (
          <Typography variant="caption" color="text.secondary" display="block">
            {formatPrice(product.attributes.unit_price)}/oz
          </Typography>
        )}

        {/* Availability & Similarity */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mt: 1,
          }}
        >
          <Tooltip title={product.availability ? "In Stock" : "Out of Stock"}>
            <Chip
              icon={
                product.availability ? (
                  <CheckCircleIcon sx={{ fontSize: "0.9rem" }} />
                ) : (
                  <CancelIcon sx={{ fontSize: "0.9rem" }} />
                )
              }
              label={product.availability ? "Available" : "Unavailable"}
              size="small"
              color={product.availability ? "success" : "error"}
              variant="outlined"
              sx={{ fontSize: "0.65rem", height: 20 }}
            />
          </Tooltip>

          <Tooltip title={`${similarityPercent}% match to your search`}>
            <Chip
              label={`${similarityPercent}%`}
              size="small"
              color={getSimilarityColor(similarityPercent)}
              sx={{ fontSize: "0.7rem", height: 20, fontWeight: 600 }}
            />
          </Tooltip>
        </Box>
      </CardContent>

      <CardActions
        sx={{ px: 2, pb: 2, pt: 0, justifyContent: "space-between" }}
      >
        <Button
          size="small"
          variant="outlined"
          startIcon={<OpenInNewIcon />}
          onClick={handleOpenProduct}
          disabled={!product.url}
        >
          View
        </Button>
        {onSave && (
          <Button
            size="small"
            variant="contained"
            startIcon={<AddShoppingCartIcon />}
            onClick={handleSave}
          >
            Save
          </Button>
        )}
      </CardActions>
    </Card>
  );
});
