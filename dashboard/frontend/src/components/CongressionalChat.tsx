import { useState, useRef, useEffect } from "react";
import {
  Box,
  TextField,
  Button,
  Paper,
  Typography,
  CircularProgress,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Link,
  Alert,
  IconButton,
  Tooltip,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import PersonIcon from "@mui/icons-material/Person";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import {
  ChatHistoryItem,
  CongressionalChatSource,
} from "../types/congressional";

interface CongressionalChatProps {
  askQuestion: (request: {
    message: string;
    member_filter?: string;
  }) => Promise<{
    answer: string;
    sources: CongressionalChatSource[];
    conversation_id: string;
    model: string;
  } | null>;
  memberFilter?: string;
  error?: string | null;
}

export function CongressionalChat({
  askQuestion,
  memberFilter,
  error: externalError,
}: CongressionalChatProps) {
  const [messages, setMessages] = useState<ChatHistoryItem[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [, setConversationId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: ChatHistoryItem = {
      id: `user-${Date.now()}`,
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await askQuestion({
        message: userMessage.content,
        member_filter: memberFilter,
      });

      if (response) {
        const assistantMessage: ChatHistoryItem = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: response.answer,
          sources: response.sources,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
        setConversationId(response.conversation_id);
      } else {
        // Error case - add error message
        const errorMessage: ChatHistoryItem = {
          id: `error-${Date.now()}`,
          role: "assistant",
          content:
            "Sorry, I encountered an error processing your question. Please try again.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    } catch (err) {
      console.error("Chat error:", err);
      const errorMessage: ChatHistoryItem = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: "An unexpected error occurred. Please try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const clearChat = () => {
    setMessages([]);
    setConversationId(null);
  };

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 500,
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 2,
        }}
      >
        <Typography variant="h6">
          Ask Questions About Congressional Data
        </Typography>
        {messages.length > 0 && (
          <Button size="small" onClick={clearChat} color="secondary">
            Clear Chat
          </Button>
        )}
      </Box>

      {/* Member filter indicator */}
      {memberFilter && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Focusing on: <strong>{memberFilter}</strong>
        </Alert>
      )}

      {/* External error */}
      {externalError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {externalError}
        </Alert>
      )}

      {/* Messages area */}
      <Paper
        variant="outlined"
        sx={{
          flex: 1,
          overflow: "auto",
          p: 2,
          mb: 2,
          bgcolor: "background.default",
          minHeight: 300,
        }}
      >
        {messages.length === 0 ? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              color: "text.secondary",
            }}
          >
            <SmartToyIcon sx={{ fontSize: 48, mb: 2, opacity: 0.5 }} />
            <Typography variant="body1" sx={{ mb: 1 }}>
              Ask me anything about Greene and Omar
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Examples:
            </Typography>
            <Box sx={{ mt: 1, textAlign: "center" }}>
              <Chip
                label="What are their positions on immigration?"
                size="small"
                onClick={() =>
                  setInput(
                    "What are Greene's and Omar's positions on immigration?",
                  )
                }
                sx={{ m: 0.5, cursor: "pointer" }}
              />
              <Chip
                label="How do they differ on healthcare?"
                size="small"
                onClick={() =>
                  setInput(
                    "How do Greene and Omar differ on healthcare policy?",
                  )
                }
                sx={{ m: 0.5, cursor: "pointer" }}
              />
              <Chip
                label="Compare their voting records"
                size="small"
                onClick={() =>
                  setInput(
                    "Compare the voting records of Greene and Omar on recent bills.",
                  )
                }
                sx={{ m: 0.5, cursor: "pointer" }}
              />
            </Box>
          </Box>
        ) : (
          <>
            {messages.map((msg) => (
              <Box
                key={msg.id}
                sx={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                  mb: 2,
                }}
              >
                {/* Message bubble */}
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 1,
                    maxWidth: "85%",
                    flexDirection: msg.role === "user" ? "row-reverse" : "row",
                  }}
                >
                  {/* Avatar */}
                  <Box
                    sx={{
                      width: 32,
                      height: 32,
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      bgcolor:
                        msg.role === "user" ? "primary.main" : "secondary.main",
                      color: "white",
                      flexShrink: 0,
                    }}
                  >
                    {msg.role === "user" ? (
                      <PersonIcon fontSize="small" />
                    ) : (
                      <SmartToyIcon fontSize="small" />
                    )}
                  </Box>

                  {/* Content */}
                  <Paper
                    elevation={1}
                    sx={{
                      p: 2,
                      bgcolor:
                        msg.role === "user"
                          ? "primary.dark"
                          : "background.paper",
                      color: msg.role === "user" ? "white" : "text.primary",
                      borderRadius: 2,
                    }}
                  >
                    <Typography
                      variant="body1"
                      sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                    >
                      {msg.content}
                    </Typography>

                    {/* Copy button for assistant messages */}
                    {msg.role === "assistant" && (
                      <Box
                        sx={{
                          mt: 1,
                          display: "flex",
                          justifyContent: "flex-end",
                        }}
                      >
                        <Tooltip title="Copy to clipboard">
                          <IconButton
                            size="small"
                            onClick={() => copyToClipboard(msg.content)}
                          >
                            <ContentCopyIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    )}
                  </Paper>
                </Box>

                {/* Sources accordion for assistant messages */}
                {msg.role === "assistant" &&
                  msg.sources &&
                  msg.sources.length > 0 && (
                    <Box sx={{ maxWidth: "85%", mt: 1, ml: 5 }}>
                      <Accordion sx={{ bgcolor: "background.paper" }}>
                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                          <Typography variant="body2" color="text.secondary">
                            Sources ({msg.sources.length})
                          </Typography>
                        </AccordionSummary>
                        <AccordionDetails>
                          {msg.sources.map((source, idx) => (
                            <Box
                              key={idx}
                              sx={{
                                mb: 1,
                                pb: 1,
                                borderBottom:
                                  idx < msg.sources!.length - 1 ? 1 : 0,
                                borderColor: "divider",
                              }}
                            >
                              <Box
                                sx={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 1,
                                  mb: 0.5,
                                }}
                              >
                                <Chip
                                  label={source.party}
                                  size="small"
                                  color={
                                    source.party === "R" ? "error" : "primary"
                                  }
                                />
                                <Typography variant="subtitle2">
                                  {source.member_name}
                                </Typography>
                              </Box>
                              <Typography
                                variant="body2"
                                sx={{ fontWeight: 500 }}
                              >
                                {source.title}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ display: "block", mt: 0.5 }}
                              >
                                {source.content_preview}
                              </Typography>
                              {source.url && (
                                <Link
                                  href={source.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  sx={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 0.5,
                                    mt: 0.5,
                                  }}
                                >
                                  <OpenInNewIcon fontSize="small" />
                                  <Typography variant="caption">
                                    View source
                                  </Typography>
                                </Link>
                              )}
                            </Box>
                          ))}
                        </AccordionDetails>
                      </Accordion>
                    </Box>
                  )}
              </Box>
            ))}

            {/* Loading indicator */}
            {loading && (
              <Box
                sx={{ display: "flex", alignItems: "center", gap: 1, ml: 5 }}
              >
                <CircularProgress size={20} />
                <Typography variant="body2" color="text.secondary">
                  Searching and generating response...
                </Typography>
              </Box>
            )}

            <div ref={messagesEndRef} />
          </>
        )}
      </Paper>

      {/* Input area */}
      <Box
        component="form"
        onSubmit={handleSubmit}
        sx={{ display: "flex", gap: 1 }}
      >
        <TextField
          inputRef={inputRef}
          fullWidth
          multiline
          maxRows={4}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about Greene and Omar..."
          disabled={loading}
          sx={{ bgcolor: "background.paper" }}
        />
        <Button
          type="submit"
          variant="contained"
          disabled={!input.trim() || loading}
          sx={{ minWidth: 100 }}
        >
          {loading ? <CircularProgress size={24} /> : <SendIcon />}
        </Button>
      </Box>

      {/* Hint */}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
        Press Enter to send, Shift+Enter for new line
      </Typography>
    </Box>
  );
}
