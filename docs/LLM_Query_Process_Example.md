# How an LLM Processes a Query: Step-by-Step

## The Query

> "Who is the current representative for AZ-09 US House?"

---

## Step 1: Tokenization (Text → Numbers)

**What is tokenization?**
Tokenization is the process of breaking text into smaller pieces called "tokens." These aren't always full words - they can be word parts, punctuation, or even single characters. The tokenizer uses a pre-built vocabulary (typically 32,000-128,000 entries) created during training using algorithms like Byte-Pair Encoding (BPE).

**Why do we need it?**
Neural networks can only process numbers, not text. Tokenization converts human-readable text into numerical IDs that the model can work with. The tokenizer is trained separately from the model and learns common patterns in text to create an efficient vocabulary.

### Token Breakdown Table

| Position | Token             | Token ID | Notes                                 |
| -------- | ----------------- | -------- | ------------------------------------- |
| 0        | `Who`             | 15546    | Question word, no leading space       |
| 1        | ` is`             | 374      | Leading space included in token       |
| 2        | ` the`            | 279      | Common word, single token             |
| 3        | ` current`        | 1510     | Adjective with leading space          |
| 4        | ` representative` | 18740    | Full word despite length              |
| 5        | ` for`            | 369      | Preposition                           |
| 6        | ` AZ`             | 23998    | State abbreviation                    |
| 7        | `-`               | 12       | Punctuation, separate token           |
| 8        | `09`              | 2545     | Number, no leading space after hyphen |
| 9        | ` US`             | 2326     | Country abbreviation                  |
| 10       | ` House`          | 4783     | Capitalized noun                      |
| 11       | `?`               | 30       | Question mark, separate token         |

**Total: 12 tokens**

```
Raw input:  "Who is the current representative for AZ-09 US House?"
                ↓
Tokenized:  ["Who", " is", " the", " current", " representative", " for", " AZ", "-", "09", " US", " House", "?"]
                ↓
Token IDs:  [15546, 374, 279, 1510, 18740, 369, 23998, 12, 2545, 2326, 4783, 30]
```

**Key observations:**

- Spaces are typically attached to the BEGINNING of tokens (not the end)
- Common words get their own single token
- Punctuation usually gets separate tokens
- Numbers and special patterns may be split unexpectedly

---

## Step 2: Embedding Lookup (IDs → Vectors)

### What is an Embedding?

An embedding is a **learned representation** of a token as a vector (a list of numbers) in a high-dimensional space. Think of it as a "coordinate" for each word in a mathematical universe where:

- **Similar meanings = nearby coordinates**
- **Different meanings = distant coordinates**
- **Relationships are preserved as directions**

Each token ID maps to exactly one row in a giant matrix called the **embedding table** (or `embed_tokens.weight` in model files).

### The Embedding Table Structure

```
Embedding Table: [vocabulary_size × hidden_size]
                 [128,000 rows   × 4,096 columns]

Row 0:      [0.012, -0.034, 0.056, ..., 0.023]  ← Token ID 0 (usually <pad> or special)
Row 1:      [0.045, 0.012, -0.078, ..., -0.034] ← Token ID 1
Row 2:      [-0.023, 0.067, 0.011, ..., 0.089]  ← Token ID 2
...
Row 15546:  [0.023, -0.041, 0.018, ..., 0.056]  ← Token ID 15546 ("Who")
...
Row 127999: [0.034, -0.012, 0.045, ..., 0.067]  ← Token ID 127999 (last token)
```

**Memory size:** 128,000 tokens × 4,096 dimensions × 2 bytes (float16) = **~1 GB** just for embeddings!

### Why Do We Need Embeddings?

**Problem:** Token IDs are arbitrary numbers with no inherent meaning.

- Token ID 15546 ("Who") and Token ID 15547 (maybe "Whom") are numerically adjacent
- But Token ID 374 (" is") is numerically far from 15546
- Yet "Who" and "is" often appear together, while "Who" and "Whom" serve similar functions

**Solution:** Embeddings encode **semantic meaning** in vectors where:

- Mathematical operations correspond to semantic operations
- Distance measures meaning similarity
- Directions encode relationships

### The Magic of Embedding Space

Embeddings are learned during training to capture relationships. Here's what makes them powerful:

#### 1. Semantic Similarity = Vector Similarity

Words with similar meanings cluster together:

```
cosine_similarity("king", "queen")     ≈ 0.85  (very similar)
cosine_similarity("king", "monarch")   ≈ 0.78  (similar)
cosine_similarity("king", "banana")    ≈ 0.12  (very different)
```

#### 2. Analogies as Vector Arithmetic

The famous example: **king - man + woman ≈ queen**

```
embed("king") - embed("man") + embed("woman") ≈ embed("queen")

This works because:
- "king" and "man" share a "male" component
- Subtracting "man" removes the "male" direction
- Adding "woman" adds the "female" direction
- Result lands near "queen" in embedding space
```

#### 3. Clustering by Category

```
COUNTRIES:        [USA, Canada, France, Japan] cluster together
ANIMALS:          [dog, cat, horse, elephant] cluster together
PROGRAMMING:      [Python, Java, function, variable] cluster together
US STATES:        [Arizona, California, Texas, Florida] cluster together
CONGRESS TERMS:   [representative, senator, congressman, delegate] cluster together
```

### How the Lookup Works (Step by Step)

```python
# Pseudocode for embedding lookup
def embed_tokens(token_ids, embedding_table):
    """
    token_ids: [15546, 374, 279, 1510, 18740, 369, 23998, 12, 2545, 2326, 4783, 30]
    embedding_table: matrix of shape [128000, 4096]
    """
    result = []
    for token_id in token_ids:
        # Simple array indexing - go to row 'token_id'
        vector = embedding_table[token_id]  # Returns 4096-dim vector
        result.append(vector)
    return stack(result)  # Shape: [12, 4096]
```

**This is NOT a neural network computation** - it's just array indexing! That's why it's called a "lookup."

### Embedding Lookup for Our Query

| Position | Token             | Token ID | Embedding Vector (showing 8 of 4096 dims)                        |
| -------- | ----------------- | -------- | ---------------------------------------------------------------- |
| 0        | `Who`             | 15546    | [0.023, -0.041, 0.018, 0.089, -0.012, 0.045, -0.034, 0.067, ...] |
| 1        | ` is`             | 374      | [-0.012, 0.033, -0.008, 0.045, 0.067, -0.023, 0.011, 0.089, ...] |
| 2        | ` the`            | 279      | [0.008, -0.015, 0.042, -0.023, 0.011, 0.056, -0.034, 0.012, ...] |
| 3        | ` current`        | 1510     | [0.045, 0.023, -0.067, 0.034, -0.089, 0.012, 0.078, -0.045, ...] |
| 4        | ` representative` | 18740    | [-0.034, 0.078, 0.023, -0.056, 0.045, 0.089, -0.012, 0.034, ...] |
| 5        | ` for`            | 369      | [0.011, -0.023, 0.056, 0.012, -0.034, -0.045, 0.067, 0.023, ...] |
| 6        | ` AZ`             | 23998    | [0.089, 0.045, -0.012, 0.067, 0.023, 0.034, -0.078, 0.011, ...]  |
| 7        | `-`               | 12       | [-0.008, 0.011, 0.034, -0.045, 0.056, 0.023, 0.012, -0.067, ...] |
| 8        | `09`              | 2545     | [0.067, -0.034, 0.045, 0.023, -0.078, -0.012, 0.089, 0.034, ...] |
| 9        | ` US`             | 2326     | [0.034, 0.056, -0.023, 0.078, 0.012, 0.067, -0.045, 0.011, ...]  |
| 10       | ` House`          | 4783     | [-0.045, 0.034, 0.089, -0.012, 0.056, 0.045, 0.023, -0.034, ...] |
| 11       | `?`               | 30       | [0.012, -0.056, 0.023, 0.045, -0.067, -0.034, 0.078, 0.011, ...] |

**Result:** A matrix of shape **[12 tokens × 4096 dimensions]**

### What Each Dimension Might Represent

While individual dimensions aren't human-interpretable, researchers have found that dimensions often encode features like:

| Dimension Range | Might Encode                                                |
| --------------- | ----------------------------------------------------------- |
| dims 0-500      | Basic syntactic features (noun vs verb, singular vs plural) |
| dims 500-1500   | Word categories (person, place, thing, action)              |
| dims 1500-3000  | Semantic associations (politics, science, emotions)         |
| dims 3000-4096  | Fine-grained distinctions, rare word features               |

**Example interpretations for our tokens:**

```
"representative" vector might have:
  - High values in "person" dimensions
  - High values in "politics/government" dimensions
  - High values in "occupation/role" dimensions
  - Moderate values in "elected official" dimensions

"AZ" vector might have:
  - High values in "location/place" dimensions
  - High values in "US state" dimensions
  - High values in "abbreviation" dimensions
  - Similar values to "Arizona" in most dimensions
```

### Semantic Relationships in Our Query

The embedding space captures these relationships:

```
Relationship 1: Location Abbreviations
distance("AZ", "Arizona") ≈ 0.15  (very close - same place)
distance("AZ", "CA") ≈ 0.25       (close - both state abbreviations)
distance("AZ", "France") ≈ 0.60   (far - different type of place)

Relationship 2: Government Roles
distance("representative", "senator") ≈ 0.20      (very close - both Congress)
distance("representative", "congressman") ≈ 0.15  (very close - synonyms)
distance("representative", "president") ≈ 0.35    (moderate - both government)
distance("representative", "teacher") ≈ 0.70      (far - different occupation)

Relationship 3: Congressional Context
distance("House", "Senate") ≈ 0.25           (close - both chambers)
distance("House", "Congress") ≈ 0.20         (close - House is part of Congress)
distance("House" [Congress], "house" [building]) ≈ 0.55  (different meanings!)
```

### How Embeddings Are Learned

During training, embeddings are adjusted so that:

1. **Tokens that appear in similar contexts get similar vectors**
   - "The representative voted..." and "The senator voted..." → representative ≈ senator

2. **Tokens that predict each other get aligned**
   - If "AZ" often appears near "Arizona", their vectors become similar

3. **The model's loss function shapes the space**
   - Vectors are optimized so the model can predict the next token accurately
   - This naturally creates meaningful structure

```
Training iteration example:
Input: "The congressman from Arizona..."
Target: next word prediction

If model predicts poorly → adjust embeddings for "congressman", "Arizona"
If model predicts well → reinforce current embeddings

After billions of examples, embeddings capture the statistical structure of language.
```

### Visualizing Embedding Space (Simplified to 2D)

If we reduced 4096 dimensions to 2D, our query tokens might look like:

```
                    QUESTIONS
                        ↑
                        │    "Who" •
                        │         "?"  •
                        │
   FUNCTION WORDS ──────┼────────────────→ CONTENT WORDS
                        │
        • " is"         │         • " representative"
        • " the"        │         • " House"
        • " for"        │
                        │    • " current"
                        │
                        │         • " AZ"
                        │         • " US"
                        │         • "09"
                        ↓
                    SPECIFICS
```

### Key Insights About Embeddings

1. **Embeddings are the model's "vocabulary of meaning"**
   - Every concept the model knows starts as an embedding lookup

2. **The embedding table is learned, not designed**
   - No human decided what dimension 347 means
   - Structure emerges from training data

3. **Same word, same embedding (initially)**
   - "House" (Congress) and "house" (building) start with the SAME embedding
   - The transformer layers later disambiguate based on context

4. **Embeddings are static after training**
   - Unlike hidden states, embeddings don't change during inference
   - They're just a lookup table frozen from training

5. **Subword tokens get their own embeddings**
   - Even partial words like "##ing" or "repr" have learned vectors
   - The model learns that "represent" + "ative" ≈ "representative"

---

## Step 3: Positional Encoding

**What is positional encoding?**
Since we feed all tokens to the model simultaneously (in parallel), we need to tell the model WHERE each token appears in the sequence. Positional encoding adds position information to each embedding vector.

**Why do we need it?**
Without position information, the model would see "dog bites man" and "man bites dog" as identical - just a bag of words. Position encoding lets the model understand word ORDER matters.

**How it works (Modern LLMs use RoPE - Rotary Position Embedding):**
Rather than adding a fixed vector, RoPE rotates the embedding vectors based on their position. This allows the model to understand both absolute position AND relative distances between tokens.

### Position Encoding Applied

| Position | Token             | Operation                  | Result                |
| -------- | ----------------- | -------------------------- | --------------------- |
| 0        | `Who`             | embed[0] + pos_encode(0)   | Position-aware vector |
| 1        | ` is`             | embed[1] + pos_encode(1)   | Position-aware vector |
| 2        | ` the`            | embed[2] + pos_encode(2)   | Position-aware vector |
| 3        | ` current`        | embed[3] + pos_encode(3)   | Position-aware vector |
| 4        | ` representative` | embed[4] + pos_encode(4)   | Position-aware vector |
| 5        | ` for`            | embed[5] + pos_encode(5)   | Position-aware vector |
| 6        | ` AZ`             | embed[6] + pos_encode(6)   | Position-aware vector |
| 7        | `-`               | embed[7] + pos_encode(7)   | Position-aware vector |
| 8        | `09`              | embed[8] + pos_encode(8)   | Position-aware vector |
| 9        | ` US`             | embed[9] + pos_encode(9)   | Position-aware vector |
| 10       | ` House`          | embed[10] + pos_encode(10) | Position-aware vector |
| 11       | `?`               | embed[11] + pos_encode(11) | Position-aware vector |

**Result:** The model now knows that "Who" comes first, "?" comes last, and can compute that "AZ" is 2 positions before "US".

---

## Step 4: Transformer Layers (The "Thinking")

**What are transformer layers?**
The core of the LLM. Each layer refines the understanding of the input by allowing tokens to "communicate" with each other (attention) and then transform their representations (feed-forward). A typical LLM has 32-80 layers.

**Why multiple layers?**

- **Early layers (1-10):** Learn syntax, grammar, basic patterns
- **Middle layers (11-20):** Learn semantic relationships, entity recognition
- **Late layers (21-32+):** Learn complex reasoning, factual recall, task-specific behavior

### 4a. Self-Attention (Tokens "Talk" to Each Other)

**What is self-attention?**
Each token creates three vectors: Query (Q), Key (K), and Value (V). The Query asks "what information do I need?", Keys advertise "what information do I have?", and Values contain the actual information to share.

**The attention calculation:**

```
Attention(Q, K, V) = softmax(Q × K^T / √d) × V
```

**For our query, here's what tokens learn from each other:**

| Token             | Attends Strongly To                | What It Learns                                  |
| ----------------- | ---------------------------------- | ----------------------------------------------- |
| `Who`             | `representative`, `House`, `?`     | This is asking about a PERSON in government     |
| ` is`             | `Who`, `representative`            | This connects a question to its subject         |
| ` the`            | `current`, `representative`        | Specificity - we want ONE particular person     |
| ` current`        | `representative`, `is`             | Temporal constraint - NOW, not historical       |
| ` representative` | `AZ`, `09`, `House`, `US`          | The role being asked about                      |
| ` for`            | `AZ`, `09`, `representative`       | Links the role to a location                    |
| ` AZ`             | `09`, `US`, `House`                | Arizona - a US state                            |
| `-`               | `AZ`, `09`                         | Connects state code to district number          |
| `09`              | `AZ`, `-`, `House`                 | District 9, a congressional district            |
| ` US`             | `House`, `representative`          | This is about US Congress                       |
| ` House`          | `representative`, `US`, `AZ`, `09` | House of Representatives (not Senate)           |
| `?`               | `Who`, `is`                        | Confirms this is a question expecting an answer |

**Multi-head attention:**
Modern LLMs use 32+ attention "heads" running in parallel. Each head can focus on different relationships:

- Head 1: Subject-verb relationships
- Head 2: Entity-location relationships
- Head 3: Question-answer patterns
- etc.

### 4b. Feed-Forward Network (Transform Each Position)

**What is the feed-forward network (FFN)?**
After attention, each token's vector passes through a neural network that transforms it. This is where much of the model's "knowledge" is stored - factual information learned during training.

**The FFN structure:**

```
Input vector (4096 dims)
    ↓
Linear layer: 4096 → 16384 (expand)
    ↓
Activation function (GELU): adds non-linearity
    ↓
Linear layer: 16384 → 4096 (compress back)
    ↓
Output vector (4096 dims)
```

**What happens in the FFN:**

- The expansion to 16384 dimensions creates space to encode many different features
- Neurons in the FFN activate for specific concepts (e.g., "US Congress", "Arizona", "politicians")
- The compression back to 4096 combines these activations into a refined representation

### 4c. Layer Normalization & Residual Connections

**Layer Norm:** Stabilizes training by normalizing vector values
**Residual Connection:** Adds the input back to the output (allows gradients to flow during training)

```
Output = LayerNorm(Attention(x) + x)
Output = LayerNorm(FFN(Output) + Output)
```

### 4d. Repeat for All Layers

```
Layer 1:  Basic syntax parsing, word relationships
Layer 8:  "AZ-09" recognized as congressional district format
Layer 16: "representative" + "House" = House of Representatives member
Layer 24: Searching learned knowledge for AZ-09 representative
Layer 32: Preparing to output factual answer about Paul Gosar
```

---

## Step 5: Final Hidden State

**What is the final hidden state?**
After passing through all transformer layers, we have a refined vector for each token position. For text generation, we only need the vector at the LAST position (position 11, the "?" token) because this contains all the accumulated context needed to predict what comes next.

```
Final hidden state at position 11: [0.892, -0.234, 0.567, 0.123, -0.456, ..., 0.789]
                                    (4096 dimensions)
```

**What this vector encodes:**
This single vector now contains a compressed representation of:

- The entire question's meaning
- The understanding that we need a person's name
- The specific knowledge about Arizona's 9th district
- The format expected for the answer

---

## Step 6: Output Projection (Vector → Vocabulary Scores)

**What is output projection?**
The final hidden state must be converted into scores for every possible next token. This is done using a linear transformation (matrix multiplication) against the output embedding matrix, often called `lm_head`.

**How it works:**
The model computes the dot product between the final hidden state and EVERY token embedding in the vocabulary:

```
For each token in vocabulary (128,000 tokens):
    score = dot_product(final_hidden_state, token_embedding)
```

**Example scores (raw logits):**

| Token            | Dot Product Score | Interpretation                                |
| ---------------- | ----------------- | --------------------------------------------- |
| `The`            | 2.34              | High - common way to start answers            |
| `Paul`           | 2.12              | High - the actual representative's first name |
| `Arizona`        | 1.89              | Medium-high - relevant to the query           |
| `Currently`      | 1.67              | Medium - another valid way to start           |
| `Representative` | 1.45              | Medium - relevant but not typical start       |
| `Greg`           | 0.23              | Low - a name, but not the right one           |
| `banana`         | -3.21             | Very low - completely irrelevant              |
| `quantum`        | -2.89             | Very low - not related to politics            |

**Why dot product?**
Tokens with embeddings that "point in the same direction" as the final hidden state get high scores. The model has learned during training to make the final hidden state point toward the embedding of the correct next token.

---

## Step 7: Softmax (Scores → Probabilities)

**What is softmax?**
Softmax converts raw scores (which can be any number) into probabilities (which must sum to 1.0). It exponentiates each score and normalizes by the sum.

**The formula:**

```
P(token_i) = exp(score_i) / Σ exp(score_j) for all j
```

**Applied to our scores:**

| Token            | Raw Score | exp(score) | Probability |
| ---------------- | --------- | ---------- | ----------- |
| `The`            | 2.34      | 10.38      | 42.3%       |
| `Paul`           | 2.12      | 8.33       | 18.7%       |
| `Arizona`        | 1.89      | 6.62       | 12.1%       |
| `Currently`      | 1.67      | 5.31       | 8.4%        |
| `Representative` | 1.45      | 4.26       | 6.2%        |
| ...              | ...       | ...        | ...         |
| `banana`         | -3.21     | 0.04       | 0.0001%     |

**Properties of softmax:**

- All probabilities are positive
- All probabilities sum to 1.0 (100%)
- Higher scores get exponentially higher probabilities
- The "winner" becomes more dominant

---

## Step 8: Token Selection (Sampling Strategy)

**What is token selection?**
Given the probability distribution, the model must choose ONE token to output. The method used depends on the "temperature" and sampling settings.

### Temperature Effects

| Temperature | Behavior                                      | Use Case              |
| ----------- | --------------------------------------------- | --------------------- |
| 0.0         | Always pick highest probability (greedy)      | Factual Q&A, code     |
| 0.7         | Moderate randomness, usually picks top tokens | General conversation  |
| 1.0         | Sample according to true probabilities        | Creative writing      |
| 1.5+        | High randomness, surprising choices           | Brainstorming, poetry |

### With Temperature = 0 (Greedy):

```
Selected: "The" (42.3% probability) ✓
```

### With Temperature = 0.7:

The probabilities are adjusted: P_new = P^(1/0.7), then renormalized.
This makes the distribution "sharper" - high probabilities get higher, low get lower.

```
Usually selects: "The" (~60% of the time)
Sometimes selects: "Paul" (~25% of the time)
Rarely selects: "Arizona" (~10% of the time)
```

### Top-K and Top-P Sampling

- **Top-K (e.g., K=40):** Only consider the top 40 tokens
- **Top-P (e.g., P=0.9):** Only consider tokens until cumulative probability reaches 90%

**For our example, let's say we selected: "The" (Token ID 791)**

---

## Step 9: Decode Token → Text

**What is decoding?**
The reverse of tokenization - converting the selected token ID back into human-readable text using the tokenizer's vocabulary lookup table.

```
Token ID: 791
    ↓
Tokenizer vocabulary lookup
    ↓
Text: "The"
```

**Output so far:** "The"

---

## Step 10: Autoregressive Loop (Repeat Until Done)

**What is autoregressive generation?**
The model generates text one token at a time. Each new token is appended to the input, and the entire process repeats. This continues until:

1. A special end-of-sequence token (`<EOS>` or `<|endoftext|>`) is generated
2. A maximum length is reached
3. A stop sequence is encountered

### Generation Trace

| Iter | Input (last part shown) | Output Token      | Why This Token?                    |
| ---- | ----------------------- | ----------------- | ---------------------------------- |
| 1    | "...US House?"          | `The`             | Common answer opener               |
| 2    | "...House? The"         | ` current`        | Echoing the question's constraint  |
| 3    | "...The current"        | ` representative` | Answering what was asked           |
| 4    | "...representative"     | ` for`            | Grammatically correct              |
| 5    | "...for"                | ` Arizona`        | Expanding "AZ" to full name        |
| 6    | "...Arizona"            | `'s`              | Possessive form                    |
| 7    | "...Arizona's"          | ` 9`              | The district number                |
| 8    | "...9"                  | `th`              | Ordinal suffix                     |
| 9    | "...9th"                | ` congressional`  | More formal than "House"           |
| 10   | "...congressional"      | ` district`       | Completing the phrase              |
| 11   | "...district"           | ` is`             | Linking to the answer              |
| 12   | "...is"                 | ` Paul`           | **The factual answer!**            |
| 13   | "...Paul"               | ` Gosar`          | Last name from training data       |
| 14   | "...Gosar"              | `,`               | Punctuation before additional info |
| 15   | "...Gosar,"             | ` a`              | Article                            |
| 16   | "...a"                  | ` Republican`     | Party affiliation                  |
| ...  | ...                     | ...               | ...                                |
| ~50  | "...2023."              | `<EOS>`           | End of response                    |

### KV Cache Optimization

**The problem:** Each iteration would require reprocessing ALL previous tokens through ALL layers - extremely slow!

**The solution:** KV Cache stores the Key and Value vectors from previous tokens. Only the NEW token needs full processing. Previous tokens' attention information is retrieved from cache.

```
Without cache: O(n² × layers) computation per token
With cache:    O(n × layers) computation per token
```

---

## Final Output

After approximately 50-100 iterations:

> "The current representative for Arizona's 9th congressional district is **Paul Gosar** (R), who has served since 2023 after redistricting moved him from AZ-04."

---

## Summary Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  INPUT: "Who is the current representative for AZ-09 US House?"         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 1: TOKENIZER                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ "Who" │ " is" │ " the" │ " current" │ " representative" │ ...  │   │
│  │ 15546 │  374  │  279   │   1510     │      18740        │ ...  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  Split text into 12 tokens, convert each to numerical ID               │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 2: EMBEDDING LOOKUP                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ ID 15546 → [0.023, -0.041, 0.018, ..., 0.056]  (4096 dims)     │   │
│  │ ID 374   → [-0.012, 0.033, -0.008, ..., 0.021] (4096 dims)     │   │
│  │ ...                                                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  Look up each token ID in embedding matrix → semantic vectors          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 3: POSITIONAL ENCODING                                            │
│  Add position information: token 0 gets pos[0], token 1 gets pos[1]... │
│  Model now knows word ORDER, not just word PRESENCE                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 4: TRANSFORMER LAYERS (×32)                                       │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  Self-Attention: Tokens communicate, share information            │ │
│  │  "Who" learns from "representative" that we need a person's name  │ │
│  │  "AZ-09" learns from "House" that this is Congress                │ │
│  ├───────────────────────────────────────────────────────────────────┤ │
│  │  Feed-Forward Network: Transform and refine each position         │ │
│  │  4096 → 16384 → 4096 with GELU activation                        │ │
│  │  Factual knowledge activated: "AZ-09 rep = Paul Gosar"           │ │
│  ├───────────────────────────────────────────────────────────────────┤ │
│  │  Layer Norm + Residual Connections: Stabilize values              │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│  Repeat 32 times. Early layers: syntax. Late layers: facts & reasoning │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 5: FINAL HIDDEN STATE                                             │
│  Take vector at last position: [0.892, -0.234, 0.567, ..., 0.123]      │
│  This 4096-dim vector encodes: "Output the name Paul Gosar"            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 6: OUTPUT PROJECTION                                              │
│  Dot product with ALL 128,000 vocabulary embeddings:                   │
│  score("The") = 2.34, score("Paul") = 2.12, score("banana") = -3.21   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 7: SOFTMAX                                                        │
│  Convert scores to probabilities:                                       │
│  "The": 42.3% | "Paul": 18.7% | "Arizona": 12.1% | "banana": 0.0001%  │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 8: TOKEN SELECTION                                                │
│  Temperature 0 → Pick "The" (highest probability)                       │
│  Temperature 0.7 → Usually "The", sometimes "Paul"                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 9: DECODE                                                         │
│  Token ID 791 → Tokenizer lookup → "The"                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
                    ┌─────────────────────────────┐
                    │  STEP 10: AUTOREGRESSIVE    │
                    │  LOOP                       │
                    │                             │
                    │  Append "The" to input     │
                    │  Repeat steps 1-9           │←─────────────┐
                    │  Until <EOS> token          │              │
                    └──────────────┬──────────────┘              │
                                   │                             │
                                   └─────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  FINAL OUTPUT                                                           │
│  "The current representative for Arizona's 9th congressional district   │
│   is Paul Gosar (R), who has served since 2023 after redistricting     │
│   moved him from AZ-04."                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways

| Step            | Input                  | Output                 | Key Concept                          |
| --------------- | ---------------------- | ---------------------- | ------------------------------------ |
| 1. Tokenization | Raw text               | Token IDs              | Text → Numbers via vocabulary lookup |
| 2. Embedding    | Token IDs              | Vectors                | Numbers → Semantic meaning           |
| 3. Position     | Vectors                | Position-aware vectors | Add word order information           |
| 4. Transformer  | Position-aware vectors | Refined vectors        | Attention + FFN = "thinking"         |
| 5. Final State  | All vectors            | Single vector          | Compress context for prediction      |
| 6. Projection   | Single vector          | Vocabulary scores      | Vector → "votes" for each word       |
| 7. Softmax      | Scores                 | Probabilities          | Make scores sum to 100%              |
| 8. Selection    | Probabilities          | One token ID           | Pick the next word                   |
| 9. Decode       | Token ID               | Text                   | Numbers → Text                       |
| 10. Loop        | New text               | Complete response      | Repeat until done                    |

---

## Important Notes

1. **The model never "understands" language** - it manipulates numerical vectors that statistically represent patterns learned from training data.

2. **All knowledge is in the weights** - The embedding table and FFN layers encode everything the model "knows" about the world.

3. **Attention is the key innovation** - It allows tokens to share information regardless of distance in the sequence.

4. **Generation is probabilistic** - The same prompt can produce different outputs depending on temperature and sampling settings.

5. **Context length is limited** - The model can only "see" a fixed number of tokens (4K, 8K, 128K, etc.) at once.

**The model never "knows" words - it only manipulates numbers. The tokenizer handles all text conversion.**

---

## Appendix: Architecture Comparison

### How Different Architectures Would Process This Query

The Transformer architecture described above is the dominant architecture today, but it wasn't always this way. Here's how different neural network architectures compare:

### Architecture Timeline

```
1980s   │ RNNs invented - Sequential, forgetting problem
1997    │ LSTMs invented - Better memory, still slow
2014    │ Seq2Seq + Attention (for translation)
2017    │ "Attention Is All You Need" - Transformers introduced
2018+   │ BERT, GPT, Claude, LLaMA - Transformer-based LLMs dominate
```

### Processing Comparison

```
                    RNN/LSTM              CNN                 TRANSFORMER
                    ─────────           ─────                 ───────────
Processing:         Sequential →        Parallel ▤           Parallel ▤
                    One at a time       Local windows         All at once

How "Who" connects to "House":

RNN:    Who → is → the → ... → House    (information passes through 10 steps)
        └──────── fades over time ─────┘

CNN:    Who ←─ 3 words ─→               (can't see "House" directly)
              House ←─ 3 words ─→
        └── need many layers to connect ──┘

Transformer:  Who ←───────────────────→ House  (DIRECT connection via attention!)
              └── single attention operation ──┘
```

### Feature Comparison

| Feature                | RNN   | LSTM   | CNN     | Transformer |
| ---------------------- | ----- | ------ | ------- | ----------- |
| **Year**               | 1980s | 1997   | 2014    | 2017        |
| **Parallelization**    | None  | None   | Partial | Full        |
| **Long-range context** | Poor  | Medium | Poor    | Excellent   |
| **Training speed**     | Slow  | Slow   | Medium  | Fast        |
| **Inference speed**    | Slow  | Slow   | Fast    | Fast        |
| **Memory scaling**     | O(n)  | O(n)   | O(n)    | O(n²)       |
| **Modern LLM use**     | No    | No     | No      | **Yes**     |

### Why Transformers Won

The key innovation is **self-attention**: every token can directly attend to every other token in a single operation, regardless of distance. This solved the "forgetting problem" of RNNs and the "local-only" limitation of CNNs.

### Hardware vs. Architecture

| Level            | What It Is             | Examples                                 |
| ---------------- | ---------------------- | ---------------------------------------- |
| **Architecture** | The algorithm/math     | Transformer, RNN, LSTM, CNN              |
| **Platform**     | Where computations run | CUDA (NVIDIA), ROCm (AMD), Metal (Apple) |
| **Hardware**     | Physical chips         | GPU, CPU, TPU                            |

**Important:** The 10-step process in this document is the **Transformer architecture**. CUDA/ROCm/Metal only determine which hardware runs these computations - the math stays the same, only the speed changes (~1000x faster on GPU vs CPU).
