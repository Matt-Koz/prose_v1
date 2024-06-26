"""
Final model wrappers. 
"""

import torch
import torch.nn as nn

from .attention_utils import get_padding_mask
from .transformer import (
    TransformerDataEncoder,
    DataOperatorDecoder,
    TransformerSymbolEncoder,
    TransformerFusion,
)
from .embedder import LinearEmbedder, LinearEmbedder_1DPDE
from logging import getLogger

logger = getLogger()


class PROSE_Fluids(nn.Module):
    """
    Wrapper for the full PROSE model (2to1).
    """

    def __init__(self, config, symbol_env, data_config):
        super().__init__()
        self.config = config
        self.symbol_env = symbol_env
        self.x_num = data_config.x_num
        self.max_output_dim = data_config.max_output_dim

        self.embedder = LinearEmbedder(config.embedder, self.x_num, self.max_output_dim)
        self.data_encoder = TransformerDataEncoder(config.data_encoder)
        # self.symbol_encoder = TransformerSymbolEncoder(config.symbol_encoder, symbol_env.equation_id2word)
        # self.fusion = TransformerFusion(config.fusion)
        self.data_decoder = DataOperatorDecoder(config.data_decoder)

    def summary(self):
        s = "\n"
        s += f"\tEmbedder:        {sum([p.numel() for p in self.embedder.parameters() if p.requires_grad]):,}\n"
        s += f"\tData Encoder:    {sum([p.numel() for p in self.data_encoder.parameters() if p.requires_grad]):,}\n"
        # s += f"\tSymbol Encoder:  {sum([p.numel() for p in self.symbol_encoder.parameters() if p.requires_grad]):,}\n"
        # s += f"\tFusion:          {sum([p.numel() for p in self.fusion.parameters() if p.requires_grad]):,}\n"
        s += f"\tData Decoder:    {sum([p.numel() for p in self.data_decoder.parameters() if p.requires_grad]):,}"
        return s

    def forward(self, mode, **kwargs):
        """
        Forward function with different forward modes.
        ### Small hack to handle PyTorch distributed.
        """
        if mode == "fwd":
            return self.fwd(**kwargs)
        elif mode == "generate":
            return self.generate(**kwargs)
        else:
            raise Exception(f"Unknown mode: {mode}")

    def fwd(
        self,
        data_input,
        input_times,
        output_times,
        symbol_input,
        symbol_padding_mask=None,
    ):
        """
        Inputs:
            data_input:             Tensor     (bs, input_len, x_num, x_num, data_dim)
            input_times:            Tensor     (bs, input_len, 1)
            output_times:           Tensor     (bs, output_len, 1)

            symbol_input:           LongTensor           (bs, symbol_len)
            symbol_padding_mask:    LongTensor           (bs, symbol_len) # True for padded elements

        Output:
            data_output:     Tensor     (bs, output_len, x_num, x_num, data_dim)
        """

        bs, input_len, x_num, _, data_dim = data_input.size()
        # symbol_len = symbol_input.size(1)
        # symbol_padding_mask = get_padding_mask(symbol_lengths)  # (bs, max_len)

        """
        Step 1: Prepare data input (add time embeddings and patch position embeddings)
            data_input (bs, input_len, x_num, x_num, data_dim) -> (bs, data_len, dim)
                       data_len = input_len * patch_num * patch_num
        """

        data_input = self.embedder.encode(data_input, input_times)  # (bs, data_len, dim)
        data_len = data_input.size(1)

        """
        Step 2: Encode + Fusion
            data_input:   Tensor     (bs, data_len, dim)
            symbol_input: LongTensor (bs, symbol_len)
        """

        data_encoded = self.data_encoder(data_input)  # (bs, data_len, dim)
        # symbol_encoded = self.symbol_encoder(
        #     symbol_input, src_key_padding_mask=symbol_padding_mask
        # )  # (bs, symbol_len, dim)

        # fused, fused_mask = self.fusion(
        #     x0=data_encoded,
        #     x1=symbol_encoded,
        #     key_padding_mask0=None,
        #     key_padding_mask1=symbol_padding_mask,
        # )  # (bs, data_len+symbol_len, dim)

        fused = data_encoded
        fused_mask = None

        """
        Step 3: Decode data
        """

        query_emb = self.data_decoder.get_query_emb(output_times)  # (bs, query_len, dim)

        data_output = self.data_decoder(
            src=fused, query_emb=query_emb, src_key_padding_mask=fused_mask
        )  # (bs, query_len, dim)

        data_output = self.embedder.decode(data_output)  # (bs, output_len, x_num, x_num, data_dim)

        return data_output

    def generate(self, **kwargs):
        return self.fwd(**kwargs)


class PROSE_1DPDE(nn.Module):
    """
    Wrapper for the full PROSE model (2to1).
    For 1D PDE
    """

    def __init__(self, config, symbol_env, data_config):
        super().__init__()
        self.config = config
        self.symbol_env = symbol_env
        self.x_num = data_config.x_num
        self.max_output_dim = data_config.max_output_dimension

        self.embedder = LinearEmbedder_1DPDE(config.embedder, self.x_num, self.max_output_dim)
        self.data_encoder = TransformerDataEncoder(config.data_encoder)
        self.symbol_encoder = TransformerSymbolEncoder(config.symbol_encoder, symbol_env.equation_id2word)
        self.fusion = TransformerFusion(config.fusion)
        self.data_decoder = DataOperatorDecoder(config.data_decoder)


    # def freeze_param(self, freeze_module):
    #     if not isinstance(freeze_module,list):
    #         freeze_module = [freeze_module]
    #     for module in freeze_module:
    #         if module == "embedder":
    #             self.embedder = freeze(self.embedder)
    #         elif module == "data_encoder":
    #             self.data_encoder = freeze(self.data_encoder)
    #         elif module == "symbol_encoder":
    #             self.symbol_encoder = freeze(self.symbol_encoder)
    #         elif module == "fusion":
    #             self.fusion =freeze(self.fusion)
    #         elif module == "data_decoder":
    #             self.data_decoder = freeze(self.ddata_decoder)
    #         else:
    #             raise f"Module {module} not in the model, unable to freeze"
    #
    # def unfreeze_param(self, unfreeze_module):
    #     if not isinstance(unfreeze_module,list):
    #         unfreeze_module = [unfreeze_module]
    #     for module in unfreeze_module:
    #         if module == "embedder":
    #             self.embedder = unfreeze(self.embedder)
    #         elif module == "data_encoder":
    #             self.data_encoder = unfreeze(self.data_encoder)
    #         elif module == "symbol_encoder":
    #             self.symbol_encoder = unfreeze(self.symbol_encoder)
    #         elif module == "fusion":
    #             self.fusion =unfreeze(self.fusion)
    #         elif module == "data_decoder":
    #             self.data_decoder = unfreeze(self.ddata_decoder)
    #         else:
    #             raise f"Module {module} not in the model, unable to unfreeze"

    def summary(self):
        s = "\n"
        s += f"\tEmbedder:        {sum([p.numel() for p in self.embedder.parameters() if p.requires_grad]):,}\n"
        s += f"\tData Encoder:    {sum([p.numel() for p in self.data_encoder.parameters() if p.requires_grad]):,}\n"
        s += f"\tSymbol Encoder:  {sum([p.numel() for p in self.symbol_encoder.parameters() if p.requires_grad]):,}\n"
        s += f"\tFusion:          {sum([p.numel() for p in self.fusion.parameters() if p.requires_grad]):,}\n"
        s += f"\tData Decoder:    {sum([p.numel() for p in self.data_decoder.parameters() if p.requires_grad]):,}"
        return s

    def forward(self, mode, **kwargs):
        """
        Forward function with different forward modes.
        ### Small hack to handle PyTorch distributed.
        """
        if mode == "fwd":
            return self.fwd(**kwargs)
        elif mode == "generate":
            return self.generate(**kwargs)
        else:
            raise Exception(f"Unknown mode: {mode}")

    def fwd(
        self,
        data_input,
        input_times,
        output_times,
        symbol_input,
        symbol_padding_mask=None,
    ):
        """
        Inputs:
            data_input:             Tensor     (bs, input_len, x_num, x_num, data_dim)
            input_times:            Tensor     (bs, input_len, 1)
            output_times:           Tensor     (bs, output_len, 1)

            symbol_input:           LongTensor           (bs, symbol_len)
            symbol_padding_mask:    LongTensor           (bs, symbol_len) # True for padded elements

        Output:
            data_output:     Tensor     (bs, output_len, x_num, x_num, data_dim)
        """
        output = {}
        bs, input_len, x_num,  data_dim = data_input.size()
        # symbol_len = symbol_input.size(1)
        # symbol_padding_mask = get_padding_mask(symbol_lengths)  # (bs, max_len)

        """
        Step 1: Prepare data input (add time embeddings and patch position embeddings)
            data_input (bs, input_len, x_num, data_dim) -> (bs, data_len, dim)
                       data_len = input_len * patch_num 
        """

        data_input = self.embedder.encode(data_input, input_times)  # (bs, data_len, dim)
        data_len = data_input.size(1)
        output["data_embeded"] = data_input
        """
        Step 2: Encode + Fusion
            data_input:   Tensor     (bs, data_len, dim)
            symbol_input: LongTensor (bs, symbol_len)
        """

        data_encoded = self.data_encoder(data_input)  # (bs, data_len, dim)
        symbol_encoded = self.symbol_encoder(
            symbol_input, src_key_padding_mask=symbol_padding_mask
        )  # (bs, symbol_len, dim)

        fused, fused_mask = self.fusion(
            x0=data_encoded,
            x1=symbol_encoded,
            key_padding_mask0=None,
            key_padding_mask1=symbol_padding_mask,
        )  # (bs, data_len+symbol_len, dim)

        # fused = data_encoded
        # fused_mask = None
        output["data_encoded"] = data_encoded
        output["symbol_encoded"] = symbol_encoded
        output["fused"] = fused
        """
        Step 3: Decode data
        """

        query_emb = self.data_decoder.get_query_emb(output_times)  # (bs, query_len, dim)

        data_output = self.data_decoder(
            src=fused, query_emb=query_emb, src_key_padding_mask=fused_mask
        )  # (bs, query_len, dim)

        data_output = self.embedder.decode(data_output)  # (bs, output_len, x_num, x_num, data_dim)

        output["data_output"] = data_output


        return output

    def generate(self, **kwargs):
        return self.fwd(**kwargs)
